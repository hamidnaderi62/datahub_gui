"""Application services for durable dataset preprocessing runs.

The service owns state transitions; a future worker can call these functions
without duplicating lifecycle rules in a view or task implementation.
"""

import csv
import hashlib
import io
import json
import os
import logging
import re
import posixpath
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from contextlib import contextmanager

import boto3
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

MAX_QUALITY_BYTES = 8 * 1024 * 1024
MAX_QUALITY_ROWS = 100_000
MAX_ARCHIVE_MEMBERS = 200_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024 * 1024  # 2 TiB
MAX_ARCHIVE_COMPRESSION_RATIO = 1000
MAX_PROFILED_IMAGES = 10_000
MAX_IMAGE_MEMBER_BYTES = 512 * 1024 * 1024
MAX_PREVIEW_ROWS = 100
MAX_CONTACT_SHEET_IMAGES = 25
CONTACT_SHEET_TILE = 192
MAX_NORMALIZED_IMAGES = 100
MAX_NORMALIZE_BYTES = 256 * 1024 * 1024
MAX_NORMALIZE_ROWS = 1_000_000
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff',
    '.avif', '.heic', '.jxl',
}
IMAGE_SIGNATURES = {
    '.jpg': lambda data: data.startswith(b'\xff\xd8\xff'),
    '.jpeg': lambda data: data.startswith(b'\xff\xd8\xff'),
    '.png': lambda data: data.startswith(b'\x89PNG\r\n\x1a\n'),
    '.gif': lambda data: data.startswith((b'GIF87a', b'GIF89a')),
    '.webp': lambda data: data[:4] == b'RIFF' and data[8:12] == b'WEBP',
    '.bmp': lambda data: data.startswith(b'BM'),
    '.tif': lambda data: data.startswith((b'II*\x00', b'MM\x00*')),
    '.tiff': lambda data: data.startswith((b'II*\x00', b'MM\x00*')),
    '.avif': lambda data: len(data) >= 12 and data[4:8] == b'ftyp' and data[8:12] in (b'avif', b'avis'),
}
KNOWN_SOURCE_EXTENSIONS = {
    '.csv', '.tsv', '.json', '.parquet', '.zip', '.tar', '.gz', '.tgz',
    '.bz2', '.xz', '.7z', '.rar', *IMAGE_EXTENSIONS,
}
PII_COLUMN_MARKERS = (
    'email',
    'e_mail',
    'phone',
    'mobile',
    'telephone',
    'ssn',
    'social_security',
    'national_id',
    'passport',
    'address',
    'street',
    'postal_code',
    'zip_code',
    'date_of_birth',
    'birth_date',
)
PII_VALUE_PATTERNS = {
    'email': re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$'),
    'phone': re.compile(r'^\+?[0-9][0-9\s().-]{7,}$'),
    'ssn': re.compile(r'^\d{3}-\d{2}-\d{4}$'),
    'national_id': re.compile(r'^\d{10}$'),
    'ipv4': re.compile(r'^(?:\d{1,3}\.){3}\d{1,3}$'),
}


class QualityGateError(Exception):
    def __init__(self, code, message=None):
        self.code = code
        super().__init__(message or code)


logger = logging.getLogger(__name__)


def _antivirus_mode():
    return str(getattr(settings, 'PIPELINE_ANTIVIRUS_MODE', 'disabled')).lower()


def scan_with_clamav(path):
    """Run an optional local ClamAV scan without making it a hard dependency."""
    mode = _antivirus_mode()
    if mode == 'disabled':
        return {'engine': 'clamav', 'status': 'skipped'}
    executable = shutil.which('clamdscan') or shutil.which('clamscan')
    if not executable:
        if mode == 'required':
            raise QualityGateError('ANTIVIRUS_UNAVAILABLE')
        return {'engine': 'clamav', 'status': 'unavailable'}
    timeout = int(getattr(settings, 'PIPELINE_ANTIVIRUS_TIMEOUT_SECONDS', 300))
    try:
        result = subprocess.run(
            [executable, '--no-summary', path],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise QualityGateError('ANTIVIRUS_TIMEOUT') from exc
    except OSError as exc:
        if mode == 'required':
            raise QualityGateError('ANTIVIRUS_UNAVAILABLE') from exc
        return {'engine': 'clamav', 'status': 'unavailable'}
    if result.returncode == 0:
        return {'engine': 'clamav', 'status': 'clean'}
    if result.returncode == 1:
        raise QualityGateError('MALWARE_DETECTED')
    raise QualityGateError('ANTIVIRUS_ERROR')


def _content_type_for_sample(raw, extension):
    if extension in IMAGE_SIGNATURES:
        return f'image/{"jpeg" if extension in (".jpg", ".jpeg") else extension.lstrip(".")}' if IMAGE_SIGNATURES[extension](raw) else None
    if raw.startswith(b'PK\x03\x04'):
        return 'application/zip'
    if raw.startswith(b'\x1f\x8b'):
        return 'application/gzip'
    if raw.startswith(b'BZh'):
        return 'application/x-bzip2'
    if raw.startswith(b'\xfd7zXZ\x00'):
        return 'application/x-xz'
    if b'\x00' in raw:
        return 'application/octet-stream'
    return 'text/plain'


def validate_source_signature(extension, raw):
    """Validate known binary signatures and reject obvious type spoofing."""
    extension = str(extension or '').lower()
    content_type = _content_type_for_sample(raw, extension)
    if extension in IMAGE_SIGNATURES and content_type is None:
        raise QualityGateError('SOURCE_TYPE_MISMATCH')
    if extension in ('.zip', '.7z', '.rar') and content_type == 'text/plain':
        raise QualityGateError('SOURCE_TYPE_MISMATCH')
    if extension in ('.csv', '.tsv', '.json') and content_type in ('application/zip', 'application/gzip', 'application/x-bzip2', 'application/x-xz'):
        raise QualityGateError('SOURCE_TYPE_MISMATCH')
    return content_type


def detect_pii_columns(columns):
    """Return conservative column-name signals for a human review gate.

    This deliberately does not inspect values, redact data, or make a legal
    classification. It only gives reviewers an explainable signal to act on.
    """
    detected = []
    for column in columns or []:
        normalized = re.sub(r'[^a-z0-9]+', '_', str(column).lower()).strip('_')
        if any(marker in normalized for marker in PII_COLUMN_MARKERS):
            detected.append(column)
    return sorted(set(detected))


def detect_pii_values(columns, rows):
    """Detect common PII-like values in a bounded sample, without storing them."""
    findings = {}
    for row in rows or []:
        for index, value in enumerate(row or []):
            text = str(value or '').strip()
            if not text:
                continue
            column = columns[index] if index < len(columns) else f'column_{index}'
            for kind, pattern in PII_VALUE_PATTERNS.items():
                if pattern.match(text):
                    entry = findings.setdefault(str(column), {'types': set(), 'count': 0})
                    entry['types'].add(kind)
                    entry['count'] += 1
                    break
    return {
        column: {'types': sorted(details['types']), 'count': details['count']}
        for column, details in findings.items()
    }


def redact_value(value):
    """Redact a scalar preview value while retaining its shape."""
    text = str(value)
    for pattern in PII_VALUE_PATTERNS.values():
        if pattern.match(text.strip()):
            return '[REDACTED]'
    return value


def redact_json(value):
    if isinstance(value, dict):
        return {key: redact_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    if isinstance(value, str):
        return redact_value(value)
    return value


from .models import (
    DatasetAsset,
    DatasetVersion,
    PipelineDefinition,
    PipelineRun,
    PipelineStepRun,
    QualityReport,
)


def enqueue_pipeline(dataset_version_id, pipeline_definition_id, requested_by=None):
    """Create or return the single idempotent run for a version/definition."""
    with transaction.atomic():
        version = (
            DatasetVersion.objects
            .select_for_update()
            .select_related('dataset')
            .get(pk=dataset_version_id)
        )
        definition = PipelineDefinition.objects.get(
            pk=pipeline_definition_id,
            is_active=True,
        )
        if version.status in (
            DatasetVersion.Status.PUBLISHED,
            DatasetVersion.Status.ARCHIVED,
        ):
            raise ValidationError('Published or archived versions cannot be reprocessed.')

        key = f'dataset-version:{version.pk}:pipeline:{definition.pk}'
        run, created = PipelineRun.objects.get_or_create(
            idempotency_key=key,
            defaults={
                'dataset_version': version,
                'pipeline_definition': definition,
                'requested_by': requested_by,
                'input_manifest': version.checksum_manifest or {},
            },
        )
        if created or run.status in (PipelineRun.Status.FAILED,):
            run.status = PipelineRun.Status.QUEUED
            run.error_code = ''
            run.finished_at = None
            run.save(update_fields=['status', 'error_code', 'finished_at'])
        if version.status in (DatasetVersion.Status.DRAFT, DatasetVersion.Status.FAILED):
            version.status = DatasetVersion.Status.PROCESSING
            version.save(update_fields=['status'])
        if version.dataset.status in ('draft', 'quarantined', 'failed'):
            version.dataset.status = 'processing'
            version.dataset.save(update_fields=['status'])
        if settings.PIPELINE_AUTO_DISPATCH and run.status == PipelineRun.Status.QUEUED:
            transaction.on_commit(
                lambda run_id=run.pk: _dispatch_pipeline_run(run_id)
            )
        return run, created


def _dispatch_pipeline_run(run_id):
    try:
        from .tasks import process_pipeline_task
        process_pipeline_task.apply_async(args=[run_id], queue='pipeline')
    except Exception:
        # Queue outages must not roll back a committed upload; the management
        # command or a later retry can process the durable queued run.
        logger.exception('Unable to dispatch pipeline run %s', run_id)


def start_pipeline_run(run_id):
    """Atomically claim a queued run for a worker."""
    with transaction.atomic():
        run = PipelineRun.objects.select_for_update().get(pk=run_id)
        if run.status == PipelineRun.Status.RUNNING:
            stale_after = timedelta(seconds=settings.PIPELINE_RUN_STALE_AFTER_SECONDS)
            if not run.started_at or run.started_at > timezone.now() - stale_after:
                raise ValidationError('Run is already being processed.')
            run.status = PipelineRun.Status.QUEUED
            run.finished_at = None
            run.save(update_fields=['status', 'finished_at'])
        if run.status != PipelineRun.Status.QUEUED:
            raise ValidationError(f'Run is not queued: {run.status}')
        run.status = PipelineRun.Status.RUNNING
        run.started_at = timezone.now()
        run.save(update_fields=['status', 'started_at'])
        steps = run.pipeline_definition.definition.get('steps', [])
        for step in steps:
            step_key = step if isinstance(step, str) else step.get('key')
            if step_key:
                PipelineStepRun.objects.get_or_create(
                    pipeline_run=run,
                    step_key=step_key,
                )
        return run


def complete_pipeline_run(run_id, result, metrics=None, score=None):
    """Record quality output and stop at human review before publication."""
    if result not in QualityReport.Result.values:
        raise ValidationError('Invalid quality result.')
    with transaction.atomic():
        run = PipelineRun.objects.select_for_update().select_related(
            'dataset_version__dataset',
        ).get(pk=run_id)
        if run.status not in (PipelineRun.Status.RUNNING, PipelineRun.Status.QUEUED):
            raise ValidationError(f'Run cannot complete from {run.status}.')
        now = timezone.now()
        run.status = PipelineRun.Status.SUCCEEDED
        run.finished_at = now
        run.output_manifest = metrics or {}
        run.save(update_fields=['status', 'finished_at', 'output_manifest'])
        QualityReport.objects.update_or_create(
            dataset_version=run.dataset_version,
            defaults={
                'result': result,
                'score': score,
                'metrics': metrics or {},
            },
        )
        version = run.dataset_version
        manifest = dict(version.checksum_manifest or {})
        manifest['pipeline'] = {
            'run_id': run.id,
            'definition_version': version.pipeline_definition_version,
            'result': result,
            'derived_assets': [
                {'asset_id': asset.id, 'object_key': asset.object_key, 'sha256': asset.sha256}
                for asset in version.assets.filter(kind='derived')
            ],
        }
        version.checksum_manifest = manifest
        version.status = DatasetVersion.Status.NEEDS_REVIEW
        version.save(update_fields=['status', 'checksum_manifest'])
        dataset = version.dataset
        dataset.status = 'needs_review'
        dataset.save(update_fields=['status'])
        return run


def fail_pipeline_run(run_id, error_code):
    """Move a failed run and its version to a terminal failed state."""
    with transaction.atomic():
        run = PipelineRun.objects.select_for_update().select_related(
            'dataset_version__dataset',
        ).get(pk=run_id)
        if run.status in (PipelineRun.Status.SUCCEEDED, PipelineRun.Status.FAILED):
            return run
        run.status = PipelineRun.Status.FAILED
        run.error_code = error_code[:120]
        run.finished_at = timezone.now()
        run.save(update_fields=['status', 'error_code', 'finished_at'])
        version = run.dataset_version
        version.status = DatasetVersion.Status.FAILED
        version.save(update_fields=['status'])
        dataset = version.dataset
        dataset.status = 'failed'
        dataset.save(update_fields=['status'])
        return run


def _read_asset_bytes(asset):
    """Read a bounded sample from local or S3-backed quarantine storage."""
    if asset.storage_bucket:
        config = settings.CLOUD_STORAGE_CONFIG
        try:
            client = boto3.client(
                's3',
                endpoint_url=config.get('S3_ENDPOINT'),
                aws_access_key_id=config.get('ACCESS_KEY'),
                aws_secret_access_key=config.get('SECRET_KEY'),
                region_name=config.get('REGION', 'us-east-1'),
                verify=True,
            )
            response = client.get_object(
                Bucket=asset.storage_bucket,
                Key=asset.object_key,
            )
            body = response['Body'].read(MAX_QUALITY_BYTES + 1)
        except Exception as exc:
            raise QualityGateError('SOURCE_NOT_READABLE') from exc
        truncated = len(body) > MAX_QUALITY_BYTES
        return body[:MAX_QUALITY_BYTES], truncated

    try:
        with default_storage.open(asset.object_key, 'rb') as source:
            body = source.read(MAX_QUALITY_BYTES + 1)
    except (OSError, FileNotFoundError) as exc:
        raise QualityGateError('SOURCE_NOT_READABLE') from exc
    truncated = len(body) > MAX_QUALITY_BYTES
    return body[:MAX_QUALITY_BYTES], truncated


@contextmanager
def _materialize_asset(asset):
    """Stream a source asset to bounded temporary disk for archive inspection."""
    digest = hashlib.sha256()
    size = 0
    with tempfile.NamedTemporaryFile(prefix='datahub-archive-', suffix='.source') as target:
        try:
            if asset.storage_bucket:
                config = settings.CLOUD_STORAGE_CONFIG
                client = boto3.client(
                    's3',
                    endpoint_url=config.get('S3_ENDPOINT'),
                    aws_access_key_id=config.get('ACCESS_KEY'),
                    aws_secret_access_key=config.get('SECRET_KEY'),
                    region_name=config.get('REGION', 'us-east-1'),
                    verify=True,
                )
                source = client.get_object(
                    Bucket=asset.storage_bucket,
                    Key=asset.object_key,
                )['Body']
            else:
                source = default_storage.open(asset.object_key, 'rb')
            try:
                for chunk in iter(lambda: source.read(8 * 1024 * 1024), b''):
                    size += len(chunk)
                    if size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                        raise QualityGateError('ARCHIVE_TOO_LARGE')
                    digest.update(chunk)
                    target.write(chunk)
            finally:
                source.close()
        except QualityGateError:
            raise
        except Exception as exc:
            raise QualityGateError('SOURCE_NOT_READABLE') from exc
        if asset.byte_size and size != asset.byte_size:
            raise QualityGateError('SOURCE_SIZE_MISMATCH')
        if asset.sha256 and digest.hexdigest() != asset.sha256:
            raise QualityGateError('CHECKSUM_MISMATCH')
        target.flush()
        yield target.name


def _archive_kind(filename):
    name = str(filename or '').lower()
    if name.endswith('.zip'):
        return 'zip'
    if name.endswith(('.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz')):
        return 'tar'
    if name.endswith(('.7z', '.rar')):
        return 'unsupported'
    return None


def _safe_archive_path(name):
    normalized = posixpath.normpath(str(name or '').replace('\\', '/'))
    return bool(normalized and normalized not in ('.', '..') and not normalized.startswith('/') and not normalized.startswith('../'))


def _archive_member_metrics(members, kind):
    member_count = 0
    directory_count = 0
    image_count = 0
    image_extensions = set()
    uncompressed_bytes = 0
    max_ratio = 0.0
    top_level = set()
    seen_names = set()
    for member in members:
        member_count += 1
        if member_count > MAX_ARCHIVE_MEMBERS:
            raise QualityGateError('ARCHIVE_MEMBER_LIMIT')
        name = member.filename if kind == 'zip' else member.name
        if not _safe_archive_path(name):
            raise QualityGateError('ARCHIVE_UNSAFE_PATH')
        normalized_name = posixpath.normpath(str(name).replace('\\', '/'))
        if normalized_name in seen_names:
            raise QualityGateError('ARCHIVE_DUPLICATE_PATH')
        seen_names.add(normalized_name)
        if kind == 'zip':
            if member.is_dir():
                directory_count += 1
                continue
            if member.flag_bits & 0x1:
                raise QualityGateError('ARCHIVE_ENCRYPTED')
            mode = (member.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise QualityGateError('ARCHIVE_LINK_NOT_ALLOWED')
            size = int(member.file_size)
            compressed = int(member.compress_size)
            if size and not compressed:
                raise QualityGateError('ARCHIVE_COMPRESSION_RATIO')
            ratio = (size / compressed) if compressed else 0.0
        else:
            if member.isdir():
                directory_count += 1
                continue
            if member.issym() or member.islnk() or not member.isfile():
                raise QualityGateError('ARCHIVE_LINK_NOT_ALLOWED')
            size = int(member.size)
            compressed = 0
            ratio = 0.0
        if ratio > MAX_ARCHIVE_COMPRESSION_RATIO:
            raise QualityGateError('ARCHIVE_COMPRESSION_RATIO')
        uncompressed_bytes += size
        if uncompressed_bytes > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise QualityGateError('ARCHIVE_UNCOMPRESSED_LIMIT')
        clean_name = str(name).replace('\\', '/')
        top_level.add(clean_name.split('/', 1)[0])
        extension = os.path.splitext(clean_name)[1].lower()
        if extension in IMAGE_EXTENSIONS:
            image_count += 1
            image_extensions.add(extension.lstrip('.'))
        max_ratio = max(max_ratio, ratio)
    if member_count == 0 or image_count == 0:
        result = 'no_images' if member_count else 'empty'
    else:
        result = 'validated'
    return {
        'archive_validation': result,
        'member_count': member_count,
        'directory_count': directory_count,
        'uncompressed_bytes': uncompressed_bytes,
        'image_count': image_count,
        'image_extensions': sorted(image_extensions),
        'top_level_entries': sorted(top_level),
        'max_compression_ratio': round(max_ratio, 2),
    }


def _profile_image_stream(stream, declared_size, extension):
    """Read one image member through a bounded spooled file for Pillow."""
    if declared_size > MAX_IMAGE_MEMBER_BYTES:
        raise QualityGateError('IMAGE_MEMBER_TOO_LARGE')
    digest = hashlib.sha256()
    total = 0
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b') as image_file:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            total += len(chunk)
            if total > MAX_IMAGE_MEMBER_BYTES:
                raise QualityGateError('IMAGE_MEMBER_TOO_LARGE')
            digest.update(chunk)
            image_file.write(chunk)
        image_file.seek(0)
        try:
            with Image.open(image_file) as image:
                image.verify()
            image_file.seek(0)
            with Image.open(image_file) as image:
                width, height = image.size
                image_format = (image.format or extension.lstrip('.')).lower()
                mode = image.mode
        except Image.DecompressionBombError as exc:
            raise QualityGateError('IMAGE_DECOMPRESSION_BOMB') from exc
        except (UnidentifiedImageError, OSError):
            return {
                'status': 'corrupt',
                'sha256': digest.hexdigest(),
                'bytes': total,
                'extension': extension.lstrip('.'),
            }
    return {
        'status': 'valid',
        'sha256': digest.hexdigest(),
        'bytes': total,
        'extension': extension.lstrip('.'),
        'format': image_format,
        'width': width,
        'height': height,
        'mode': mode,
    }


def _profile_archive_images(archive, members, kind):
    """Profile image members while keeping archive contents out of storage."""
    profiles = []
    hashes = set()
    duplicate_count = 0
    corrupt_count = 0
    format_counts = {}
    dimensions = []
    profile_limit_reached = False
    for member in members:
        name = member.filename if kind == 'zip' else member.name
        extension = os.path.splitext(str(name).replace('\\', '/'))[1].lower()
        if extension not in IMAGE_EXTENSIONS:
            continue
        if len(profiles) >= MAX_PROFILED_IMAGES:
            profile_limit_reached = True
            break
        if kind == 'zip':
            if member.is_dir():
                continue
            stream = archive.open(member, 'r')
            declared_size = int(member.file_size)
        else:
            if not member.isfile():
                continue
            stream = archive.extractfile(member)
            if stream is None:
                corrupt_count += 1
                continue
            declared_size = int(member.size)
        try:
            profile = _profile_image_stream(stream, declared_size, extension)
        finally:
            stream.close()
        if profile['sha256'] in hashes:
            duplicate_count += 1
        else:
            hashes.add(profile['sha256'])
        if profile['status'] == 'corrupt':
            corrupt_count += 1
        else:
            format_counts[profile['format']] = format_counts.get(profile['format'], 0) + 1
            dimensions.append((profile['width'], profile['height']))
        profiles.append({key: value for key, value in profile.items() if key != 'sha256'})
    result = {
        'sampled_count': len(profiles),
        'corrupt_count': corrupt_count,
        'duplicate_count': duplicate_count,
        'profile_limit_reached': profile_limit_reached,
        'format_counts': format_counts,
        'profiles': profiles[:100],
    }
    if dimensions:
        result['dimensions'] = {
            'min_width': min(width for width, _ in dimensions),
            'max_width': max(width for width, _ in dimensions),
            'min_height': min(height for _, height in dimensions),
            'max_height': max(height for _, height in dimensions),
        }
    return result


def _archive_image_streams(path, archive_kind):
    """Yield bounded image streams from an already materialized archive."""
    if archive_kind == 'zip':
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            for member in members:
                name = member.filename
                extension = os.path.splitext(str(name).replace('\\', '/'))[1].lower()
                if member.is_dir() or extension not in IMAGE_EXTENSIONS or member.file_size > MAX_IMAGE_MEMBER_BYTES:
                    continue
                stream = archive.open(member, 'r')
                try:
                    yield stream, extension, name
                finally:
                    stream.close()
        return
    archive = tarfile.open(path, mode='r:*')
    try:
        for member in archive.getmembers():
            extension = os.path.splitext(str(member.name).replace('\\', '/'))[1].lower()
            if not member.isfile() or extension not in IMAGE_EXTENSIONS or member.size > MAX_IMAGE_MEMBER_BYTES:
                continue
            stream = archive.extractfile(member)
            if stream is None:
                continue
            try:
                yield stream, extension, member.name
            finally:
                stream.close()
    finally:
        archive.close()


def create_image_contact_sheet(asset, archive_kind):
    """Create a bounded JPEG contact sheet without persisting extracted files."""
    thumbnails = []
    with _materialize_asset(asset) as path:
        for stream, extension, _name in _archive_image_streams(path, archive_kind):
            if len(thumbnails) >= MAX_CONTACT_SHEET_IMAGES:
                break
            try:
                with Image.open(stream) as image:
                    image.verify()
                stream.seek(0)
                with Image.open(stream) as image:
                    thumbnail = image.convert('RGB')
                    thumbnail.thumbnail((CONTACT_SHEET_TILE - 16, CONTACT_SHEET_TILE - 16))
                    thumbnails.append(thumbnail.copy())
            except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
                continue
    if not thumbnails:
        return None
    columns = min(5, len(thumbnails))
    rows = (len(thumbnails) + columns - 1) // columns
    sheet = Image.new('RGB', (columns * CONTACT_SHEET_TILE, rows * CONTACT_SHEET_TILE), 'white')
    for index, thumbnail in enumerate(thumbnails):
        x = (index % columns) * CONTACT_SHEET_TILE
        y = (index // columns) * CONTACT_SHEET_TILE
        left = x + (CONTACT_SHEET_TILE - thumbnail.width) // 2
        top = y + (CONTACT_SHEET_TILE - thumbnail.height) // 2
        sheet.paste(thumbnail, (left, top))
        thumbnail.close()
    output = io.BytesIO()
    sheet.save(output, format='JPEG', quality=85, optimize=True)
    sheet.close()
    return output.getvalue()


def create_normalized_images(source_asset, quality_metrics):
    """Create bounded RGB/JPEG derivatives for the first safe image members."""
    archive_kind = _archive_kind(source_asset.original_name or source_asset.object_key)
    if archive_kind not in ('zip', 'tar'):
        return [], {'status': 'not_applicable'}
    if not quality_metrics.get('image_profile', {}).get('sampled_count'):
        return [], {'status': 'no_images'}
    assets = []
    manifest = []
    with _materialize_asset(source_asset) as path:
        for index, (stream, extension, name) in enumerate(_archive_image_streams(path, archive_kind)):
            if index >= MAX_NORMALIZED_IMAGES:
                break
            try:
                with Image.open(stream) as image:
                    image.verify()
                stream.seek(0)
                with Image.open(stream) as image:
                    normalized = image.convert('RGB')
                    output = io.BytesIO()
                    normalized.save(output, format='JPEG', quality=90, optimize=True)
                    normalized.close()
                key = f'normalized/{source_asset.dataset_version_id}/asset-{source_asset.id}/image-{index:05d}.jpg'
                stored = store_derived_asset(source_asset, key, output.getvalue(), 'image/jpeg', kind=DatasetAsset.Kind.DERIVED)
                assets.append(stored)
                manifest.append({'source_path': name, 'object_key': stored.object_key, 'sha256': stored.sha256, 'bytes': stored.byte_size, 'format': 'jpeg'})
            except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
                continue
    return assets, {'status': 'created' if assets else 'no_valid_images', 'count': len(assets), 'limit': MAX_NORMALIZED_IMAGES, 'assets': manifest}


def create_tabular_preview(raw, extension, quality_metrics=None):
    """Create a small, bounded preview file for CSV/TSV/JSON sources."""
    if extension in ('.csv', '.tsv'):
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            return None
        delimiter = '\t' if extension == '.tsv' else ','
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = []
        for row in reader:
            if rows:
                pii_columns = set((quality_metrics or {}).get('pii_columns', []))
                row = [
                    '[REDACTED]' if index < len(rows[0]) and (rows[0][index] in pii_columns or PII_VALUE_PATTERNS['email'].match(str(value).strip()) or PII_VALUE_PATTERNS['phone'].match(str(value).strip()) or PII_VALUE_PATTERNS['ssn'].match(str(value).strip())) else value
                    for index, value in enumerate(row)
                ]
            rows.append(row)
            if len(rows) >= MAX_PREVIEW_ROWS + 1:
                break
        if not rows:
            return None
        output = io.StringIO()
        csv.writer(output, delimiter=delimiter, lineterminator='\n').writerows(rows)
        return output.getvalue().encode('utf-8'), 'text/tab-separated-values' if extension == '.tsv' else 'text/csv', extension
    if extension == '.json':
        try:
            payload = json.loads(raw.decode('utf-8-sig'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if isinstance(payload, list):
            payload = payload[:MAX_PREVIEW_ROWS]
        payload = redact_json(payload)
        return json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8'), 'application/json', '.json'
    return None


def store_derived_asset(source_asset, object_key, payload, media_type, kind=DatasetAsset.Kind.PREVIEW):
    """Store a generated artifact beside its source and register its checksum."""
    bucket = source_asset.storage_bucket
    if bucket:
        config = settings.CLOUD_STORAGE_CONFIG
        client = boto3.client(
            's3',
            endpoint_url=config.get('S3_ENDPOINT'),
            aws_access_key_id=config.get('ACCESS_KEY'),
            aws_secret_access_key=config.get('SECRET_KEY'),
            region_name=config.get('REGION', 'us-east-1'),
            verify=True,
        )
        client.put_object(Bucket=bucket, Key=object_key, Body=payload, ContentType=media_type)
    else:
        if default_storage.exists(object_key):
            default_storage.delete(object_key)
        default_storage.save(object_key, ContentFile(payload))
    return DatasetAsset.objects.update_or_create(
        dataset_version=source_asset.dataset_version,
        object_key=object_key,
        defaults={
            'kind': kind,
            'storage_bucket': bucket,
            'original_name': os.path.basename(object_key),
            'media_type': media_type,
            'byte_size': len(payload),
            'sha256': hashlib.sha256(payload).hexdigest(),
            'status': 'validated',
        },
    )[0]


def create_preview_asset(source_asset, quality_metrics):
    """Generate a preview only after the source has passed safety checks."""
    extension = os.path.splitext(source_asset.original_name or source_asset.object_key)[1].lower()
    archive_kind = _archive_kind(source_asset.original_name or source_asset.object_key)
    if archive_kind in ('zip', 'tar') and quality_metrics.get('image_profile', {}).get('sampled_count'):
        payload = create_image_contact_sheet(source_asset, archive_kind)
        if payload:
            key = f'previews/{source_asset.dataset_version_id}/asset-{source_asset.id}-contact-sheet.jpg'
            return store_derived_asset(source_asset, key, payload, 'image/jpeg')
    if extension in ('.csv', '.tsv', '.json'):
        raw, _ = _read_asset_bytes(source_asset)
        preview = create_tabular_preview(raw, extension, quality_metrics)
        if preview:
            payload, media_type, output_extension = preview
            key = f'previews/{source_asset.dataset_version_id}/asset-{source_asset.id}{output_extension}'
            return store_derived_asset(source_asset, key, payload, media_type)
    return None


def create_normalized_parquet(source_asset):
    """Create a bounded, reproducible Parquet representation for tabular data."""
    extension = os.path.splitext(source_asset.original_name or source_asset.object_key)[1].lower()
    if extension not in ('.csv', '.tsv', '.json'):
        return None, {'status': 'not_applicable'}
    if source_asset.byte_size > MAX_NORMALIZE_BYTES:
        return None, {'status': 'skipped_size_limit', 'max_bytes': MAX_NORMALIZE_BYTES}

    try:
        import pandas as pd

        with _materialize_asset(source_asset) as path:
            if extension in ('.csv', '.tsv'):
                frame = pd.read_csv(
                    path,
                    sep='\t' if extension == '.tsv' else ',',
                    nrows=MAX_NORMALIZE_ROWS + 1,
                )
            else:
                with open(path, 'r', encoding='utf-8-sig') as source:
                    payload = json.load(source)
                if isinstance(payload, list):
                    if len(payload) > MAX_NORMALIZE_ROWS:
                        return None, {'status': 'skipped_row_limit', 'max_rows': MAX_NORMALIZE_ROWS}
                    frame = pd.json_normalize(payload)
                elif isinstance(payload, dict):
                    frame = pd.json_normalize([payload])
                else:
                    return None, {'status': 'skipped_json_shape'}
            if len(frame.index) > MAX_NORMALIZE_ROWS:
                return None, {'status': 'skipped_row_limit', 'max_rows': MAX_NORMALIZE_ROWS}
            if frame.columns.empty:
                return None, {'status': 'skipped_empty_schema'}
            frame.columns = [str(column).strip() or f'column_{index}' for index, column in enumerate(frame.columns)]
            frame = frame.loc[:, ~frame.columns.duplicated()]
            output = io.BytesIO()
            frame.to_parquet(output, engine='pyarrow', index=False, compression='snappy')
            payload = output.getvalue()
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError, ImportError) as exc:
        logger.warning('Tabular normalization failed for asset %s: %s', source_asset.pk, exc)
        return None, {'status': 'failed', 'error': 'NORMALIZATION_FAILED'}
    except Exception:
        logger.exception('Unexpected tabular normalization failure for asset %s', source_asset.pk)
        return None, {'status': 'failed', 'error': 'NORMALIZATION_FAILED'}

    object_key = f'normalized/{source_asset.dataset_version_id}/asset-{source_asset.id}.parquet'
    normalized = store_derived_asset(
        source_asset,
        object_key,
        payload,
        'application/vnd.apache.parquet',
        kind=DatasetAsset.Kind.DERIVED,
    )
    return normalized, {
        'status': 'created',
        'normalization_version': 'tabular-parquet-v1',
        'input_sha256': source_asset.sha256,
        'asset_id': normalized.id,
        'object_key': normalized.object_key,
        'sha256': normalized.sha256,
        'rows': int(len(frame.index)),
        'columns': [str(column) for column in frame.columns],
        'bytes': normalized.byte_size,
        'format': 'parquet',
        'compression': 'snappy',
    }


def inspect_archive_asset(asset, archive_kind):
    """Inspect archive metadata without extracting untrusted member files."""
    if archive_kind == 'unsupported':
        with _materialize_asset(asset) as path:
            security = scan_with_clamav(path)
        return {
            'archive_validation': 'unsupported_format',
            'member_count': None,
            'image_count': None,
            'inspection': 'metadata_only',
            'security_scan': security,
        }
    with _materialize_asset(asset) as path:
        security = scan_with_clamav(path)
        try:
            if archive_kind == 'zip':
                with zipfile.ZipFile(path) as archive:
                    members = archive.infolist()
                    metrics = _archive_member_metrics(members, 'zip')
                    metrics['image_profile'] = _profile_archive_images(archive, members, 'zip')
            else:
                with tarfile.open(path, mode='r:*') as archive:
                    members = archive.getmembers()
                    metrics = _archive_member_metrics(members, 'tar')
                    metrics['image_profile'] = _profile_archive_images(archive, members, 'tar')
        except QualityGateError:
            raise
        except (zipfile.BadZipFile, tarfile.TarError, EOFError) as exc:
            raise QualityGateError('ARCHIVE_INVALID') from exc
    metrics['security_scan'] = security
    return metrics


def inspect_source_asset(asset):
    """Compute bounded, format-aware quality metrics for one source asset."""
    extension_name = asset.original_name or asset.object_key
    extension = os.path.splitext(str(extension_name))[1].lower()
    if bool(getattr(settings, 'PIPELINE_STRICT_FILE_TYPES', False)) and extension not in KNOWN_SOURCE_EXTENSIONS:
        raise QualityGateError('SOURCE_TYPE_NOT_ALLOWED')
    archive_kind = _archive_kind(extension_name)
    if archive_kind:
        metrics = {
            'object_key': asset.object_key,
            'format': os.path.splitext(str(extension_name))[1].lstrip('.').lower() or 'archive',
            'archive_format': archive_kind,
            'content_type': 'application/zip' if archive_kind == 'zip' else ('application/x-tar' if archive_kind == 'tar' else 'application/octet-stream'),
            'bytes_sampled': min(asset.byte_size, MAX_QUALITY_BYTES),
            'truncated': asset.byte_size > MAX_QUALITY_BYTES,
        }
        metrics.update(inspect_archive_asset(asset, archive_kind))
        metrics['pii_columns'] = []
        metrics['pii_detected'] = False
        return metrics
    raw, truncated = _read_asset_bytes(asset)
    digest = hashlib.sha256(raw).hexdigest() if not truncated else None
    if digest and asset.sha256 and digest != asset.sha256:
        raise QualityGateError('CHECKSUM_MISMATCH')

    content_type = validate_source_signature(extension, raw)
    security = {'engine': 'clamav', 'status': 'skipped'}
    if _antivirus_mode() != 'disabled':
        with _materialize_asset(asset) as path:
            security = scan_with_clamav(path)
    metrics = {
        'object_key': asset.object_key,
        'format': extension.lstrip('.') or 'unknown',
        'bytes_sampled': len(raw),
        'truncated': truncated,
        'content_type': content_type,
        'security_scan': security,
    }
    if extension in ('.csv', '.tsv'):
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise QualityGateError('SOURCE_DECODE_FAILED') from exc
        delimiter = '\t' if extension == '.tsv' else ','
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        try:
            columns = next(reader)
        except StopIteration as exc:
            raise QualityGateError('SOURCE_EMPTY') from exc
        if not columns or any(not column.strip() for column in columns):
            raise QualityGateError('SCHEMA_INVALID')
        if len(columns) != len(set(columns)):
            raise QualityGateError('DUPLICATE_COLUMNS')
        rows = 0
        null_values = 0
        sampled_rows = []
        for row in reader:
            rows += 1
            null_values += sum(1 for value in row if not value.strip())
            if len(sampled_rows) < MAX_PREVIEW_ROWS:
                sampled_rows.append(row)
            if rows >= MAX_QUALITY_ROWS:
                break
        value_pii = detect_pii_values(columns, sampled_rows)
        metrics.update({
            'columns': columns,
            'column_count': len(columns),
            'rows_sampled': rows,
            'null_values_sampled': null_values,
            'value_pii_columns': value_pii,
            'value_pii_detected': bool(value_pii),
        })
    elif extension == '.json':
        try:
            payload = json.loads(raw.decode('utf-8-sig'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise QualityGateError('SOURCE_JSON_INVALID') from exc
        if isinstance(payload, list):
            metrics['rows_sampled'] = min(len(payload), MAX_QUALITY_ROWS)
            metrics['json_shape'] = 'array'
            if payload and isinstance(payload[0], dict):
                metrics['columns'] = list(payload[0].keys())
                metrics['column_count'] = len(metrics['columns'])
                metrics['value_pii_columns'] = detect_pii_values(
                    metrics['columns'],
                    [[item.get(column, '') for column in metrics['columns']] for item in payload[:MAX_PREVIEW_ROWS] if isinstance(item, dict)],
                )
        elif isinstance(payload, dict):
            metrics['rows_sampled'] = 1
            metrics['columns'] = list(payload.keys())
            metrics['column_count'] = len(metrics['columns'])
            metrics['json_shape'] = 'object'
            metrics['value_pii_columns'] = detect_pii_values(
                metrics['columns'], [[payload.get(column, '') for column in metrics['columns']]]
            )
        else:
            raise QualityGateError('SOURCE_JSON_SHAPE_INVALID')
    else:
        metrics['inspection'] = 'metadata_only'

    columns = metrics.get('columns', [])
    metrics.setdefault('value_pii_columns', {})
    metrics['value_pii_detected'] = bool(metrics['value_pii_columns'])
    pii_columns = detect_pii_columns(columns)
    metrics['pii_columns'] = pii_columns
    metrics['pii_detected'] = bool(pii_columns)

    return metrics


def process_pipeline_run(run_id):
    """Run bounded checksum/schema checks and stop at human review."""
    run = start_pipeline_run(run_id)
    logger.info('pipeline_run_started', extra={'pipeline_run_id': run.id, 'dataset_version_id': run.dataset_version_id})
    assets = list(run.dataset_version.assets.filter(kind='source'))
    if not assets:
        return fail_pipeline_run(run.id, 'SOURCE_ASSET_MISSING')
    invalid_assets = [
        asset for asset in assets
        if asset.byte_size <= 0 or len(asset.sha256) != 64
    ]
    if invalid_assets:
        return fail_pipeline_run(run.id, 'SOURCE_METADATA_INVALID')

    try:
        quality_assets = [inspect_source_asset(asset) for asset in assets]
    except QualityGateError as exc:
        return fail_pipeline_run(run.id, exc.code)
    except Exception:
        return fail_pipeline_run(run.id, 'QUALITY_GATE_FAILED')

    privacy_plan = (run.dataset_version.checksum_manifest or {}).get('privacy_plan')
    if isinstance(privacy_plan, dict) and privacy_plan.get('fail_on_residual_pii'):
        residual_assets = [
            metrics for metrics in quality_assets
            if metrics.get('value_pii_detected')
        ]
        if residual_assets:
            return complete_pipeline_run(
                run.id,
                QualityReport.Result.FAIL,
                metrics={
                    'validation': 'residual_pii_detected',
                    'privacy_plan': privacy_plan,
                    'assets': quality_assets,
                    'residual_assets': len(residual_assets),
                },
                score='0.00',
            )

    generated_assets = []
    for asset, quality_metrics in zip(assets, quality_assets):
        try:
            preview = create_preview_asset(asset, quality_metrics)
        except QualityGateError as exc:
            quality_metrics['preview_error'] = exc.code
            logger.warning('Preview generation rejected for asset %s: %s', asset.pk, exc.code)
            preview = None
        except Exception:
            quality_metrics['preview_error'] = 'PREVIEW_GENERATION_FAILED'
            logger.exception('Preview generation failed for asset %s', asset.pk)
            preview = None
        if preview:
            generated_assets.append({
                'asset_id': preview.id,
                'object_key': preview.object_key,
                'kind': preview.kind,
                'media_type': preview.media_type,
                'byte_size': preview.byte_size,
            })
        try:
            normalized, normalization = create_normalized_parquet(asset)
            quality_metrics['normalization'] = normalization
        except Exception:
            quality_metrics['normalization'] = {'status': 'failed', 'error': 'NORMALIZATION_FAILED'}
            logger.exception('Normalization failed for asset %s', asset.pk)
            normalized = None
        if normalized:
            generated_assets.append({
                'asset_id': normalized.id,
                'object_key': normalized.object_key,
                'kind': normalized.kind,
                'media_type': normalized.media_type,
                'byte_size': normalized.byte_size,
            })
        try:
            normalized_images, image_normalization = create_normalized_images(asset, quality_metrics)
            quality_metrics['image_normalization'] = image_normalization
        except Exception:
            quality_metrics['image_normalization'] = {'status': 'failed', 'error': 'IMAGE_NORMALIZATION_FAILED'}
            logger.exception('Image normalization failed for asset %s', asset.pk)
            normalized_images = []
        for normalized_image in normalized_images:
            generated_assets.append({
                'asset_id': normalized_image.id,
                'object_key': normalized_image.object_key,
                'kind': normalized_image.kind,
                'media_type': normalized_image.media_type,
                'byte_size': normalized_image.byte_size,
            })

    total_bytes = sum(asset.byte_size for asset in assets)
    for step in run.steps.all():
        step.status = PipelineStepRun.Status.RUNNING
        step.attempt += 1
        step.started_at = timezone.now()
        step.save(update_fields=['status', 'attempt', 'started_at'])
        step.status = PipelineStepRun.Status.SUCCEEDED
        step.metrics = {'source_assets': len(assets), 'bytes': total_bytes}
        step.finished_at = timezone.now()
        step.save(update_fields=['status', 'metrics', 'finished_at'])
    for asset in assets:
        asset.status = 'validated'
        asset.save(update_fields=['status'])

    completed = complete_pipeline_run(
        run.id,
        QualityReport.Result.REVIEW,
        metrics={
            'source_assets': len(assets),
            'bytes': total_bytes,
            'validation': 'bounded_quality_gate',
            'assets': quality_assets,
            'derived_assets': generated_assets,
        },
        score='100.00',
    )
    logger.info('pipeline_run_completed', extra={'pipeline_run_id': completed.id, 'dataset_version_id': completed.dataset_version_id, 'derived_assets': len(generated_assets)})
    return completed


def publish_dataset_version(version_id, actor):
    """Publish a reviewed immutable version through an authorized transition."""
    if not getattr(actor, 'is_authenticated', False):
        raise PermissionDenied('Authentication is required to publish a dataset.')
    with transaction.atomic():
        version = (
            DatasetVersion.objects
            .select_for_update()
            .select_related('dataset')
            .get(pk=version_id)
        )
        if not (actor.is_superuser or version.dataset.user_id == actor.pk):
            raise PermissionDenied('Only the dataset owner or an administrator can publish it.')
        if version.status == DatasetVersion.Status.PUBLISHED:
            return version
        if version.status != DatasetVersion.Status.NEEDS_REVIEW:
            raise ValidationError('Only versions awaiting review can be published.')
        quality_report = QualityReport.objects.filter(
            dataset_version=version,
        ).first()
        if quality_report is None:
            raise ValidationError('A quality report is required before publication.')
        if quality_report.result == QualityReport.Result.FAIL:
            raise ValidationError('A failed quality report cannot be published.')

        now = timezone.now()
        version.status = DatasetVersion.Status.PUBLISHED
        version.published_at = now
        version.published_by = actor
        version.save(update_fields=['status', 'published_at', 'published_by'])
        version.assets.update(status='published')
        dataset = version.dataset
        dataset.status = 'published'
        dataset.save(update_fields=['status'])
        return version

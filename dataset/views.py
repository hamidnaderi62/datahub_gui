from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import render, get_object_or_404
from .models import (
    Dataset, User, Comment, PredefinedTag, Request, AnnotationRequest,
    AnnotationResponse, DatasetVersion, DatasetAsset, PipelineDefinition, QualityReport,
    UploadBatch, UploadSession, UploadPart,
)
from django.urls import reverse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.files.storage import default_storage
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.views.decorators.http import require_POST
import pandas as pd
from fastparquet import ParquetFile
import pygwalker as pyg
import os
from django.conf import settings
from djangoaddicts.pygwalker.views import PygWalkerView
from django.utils.html import format_html
from djangoaddicts.pygwalker.views import StaticCsvPygWalkerView
from djangoaddicts.pygwalker.views import PygWalkerView
import json
from datetime import datetime, timedelta
from taggit.models import Tag
from django.db.models import Count
import math
from django.views.generic import TemplateView
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.core.exceptions import PermissionDenied, ValidationError

import re
import requests
import hashlib
import logging
from datetime import datetime
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from .models import Dataset
import boto3
from botocore.client import Config
import uuid
import tempfile
import ssl
from botocore.exceptions import ClientError
from .pipeline import enqueue_pipeline, publish_dataset_version
from marketplace.services import has_active_entitlement

logger = logging.getLogger(__name__)

def can_access_dataset(user, dataset):
    # Paid data requires an active entitlement for a published version.
    if user.is_authenticated and (user.is_superuser or dataset.user_id == user.pk):
        return True
    if dataset.price != 0:
        return has_active_entitlement(user, dataset)
    if dataset.requestRequired == 'No':
        return True
    if dataset.requestRequired != 'Yes' or not user.is_authenticated:
        return False
    return Request.objects.filter(
        dataset=dataset, user=user, responseType='Accept'
    ).exists()


def dataset_list_fa(request):
    DATASETS_PER_PAGE = 15
    q = request.GET.get('q')
    all_datasets = Dataset.objects.all()
    if q:
        all_datasets = all_datasets.filter(dataset_tags__icontains=q)
    all_datasets = all_datasets.order_by('-id')
    paginator = Paginator(all_datasets, DATASETS_PER_PAGE)
    page_number = request.GET.get('page')
    try:
        datasets = paginator.get_page(page_number)
    except PageNotAnInteger:
        datasets = paginator.get_page(1)
    except EmptyPage:
        datasets = paginator.get_page(paginator.num_pages)
    return render(request, 'dataset/dataset_list.html', {'datasets': datasets})


def dataset_detail_fa(request, pk=None):
    dataset = get_object_or_404(Dataset.objects.prefetch_related('tags'), id=pk)
    # Share providers need an absolute URL and this also works behind a proxy.
    share_url = request.build_absolute_uri(
        reverse('dataset:dataset_detail', kwargs={'pk': dataset.pk})
    )
    latest_version = dataset.versions.prefetch_related('assets', 'pipeline_runs').order_by('-version').first()
    quality_report = QualityReport.objects.filter(dataset_version=latest_version).first() if latest_version else None
    tags = dataset.tags.all()
    similar_datasets = (
        Dataset.objects.filter(tags__in=tags)
        .exclude(id=dataset.id)
        .annotate(num_common_tags=Count('tags'))
        .order_by('-num_common_tags')[:3]
    )
    context = {
        'dataset': dataset,
        'similar_datasets': similar_datasets,
        'latest_version': latest_version,
        'quality_report': quality_report,
        'share_url': share_url,
    }

    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if 'submit_dataset_comment' in request.POST:
            text = request.POST.get('text', '').strip()
            if text:
                label, score = analyze_sentiment(text)
                Comment.objects.create(
                    text=text, dataset=dataset,
                    user=request.user, sentiment_label=label, sentiment_score=score
                )
        elif 'submit_dataset_request' in request.POST:
            if dataset.user_id != request.user.pk and not Request.objects.filter(
                dataset=dataset, user=request.user
            ).exists():
                Request.objects.create(dataset=dataset, user=request.user)
        elif 'submit_dataset_viewer' in request.POST:
            if not can_access_dataset(request.user, dataset):
                raise PermissionDenied
            try:
                df = pd.read_csv(dataset.file.path)
                html_obj = pyg.walk(df[:10], return_html=True)
                context['html_obj'] = html_obj
                return render(request, 'dataset/dataset_detail.html', context)
            except FileNotFoundError:
                raise PermissionDenied("Dataset file not found.")

    return render(request, 'dataset/dataset_detail.html', context)


@login_required
@require_POST
def publish_dataset_version_fa(request, version_id):
    try:
        version = publish_dataset_version(version_id, request.user)
    except ValidationError as exc:
        return JsonResponse({
            'status': 'error',
            'message': exc.messages[0] if exc.messages else 'Publication is not allowed.',
            'code': 'PUBLICATION_NOT_ALLOWED',
        }, status=400)
    return JsonResponse({
        'status': 'success',
        'dataset_id': version.dataset_id,
        'dataset_version_id': version.id,
        'version_status': version.status,
    })


@login_required
def pipeline_status(request, version_id):
    """Return owner-scoped pipeline progress for review pages and polling clients."""
    version = get_object_or_404(
        DatasetVersion.objects.select_related('dataset').prefetch_related('pipeline_runs__steps'),
        pk=version_id,
    )
    if not (request.user.is_superuser or version.dataset.user_id == request.user.pk):
        raise PermissionDenied
    run = version.pipeline_runs.order_by('-created_at').first()
    quality = QualityReport.objects.filter(dataset_version=version).first()
    return JsonResponse({
        'status': 'success',
        'dataset_id': version.dataset_id,
        'version_id': version.id,
        'version_status': version.status,
        'pipeline_run_id': run.id if run else None,
        'pipeline_status': run.status if run else None,
        'steps': [
            {'key': step.step_key, 'status': step.status, 'attempt': step.attempt, 'metrics': step.metrics}
            for step in (run.steps.all() if run else [])
        ],
        'quality_report': quality.metrics if quality else None,
    })


@login_required
def dataset_download_fa(request, pk=None):
    dataset = get_object_or_404(Dataset, id=pk)
    if not can_access_dataset(request.user, dataset):
        raise PermissionDenied
    return render(request, 'dataset/dataset_download.html', context={'dataset': dataset})


@login_required
@require_POST
def dataset_like_fa(request, pk):
    dataset = get_object_or_404(Dataset, id=pk)
    if request.user in dataset.likes.all():
        dataset.likes.remove(request.user)
        liked = False
    else:
        dataset.likes.add(request.user)
        liked = True
    return JsonResponse({'liked': liked, 'total_likes': dataset.likes.count()})


def predefined_tags(request):
    dataset_tags = list(PredefinedTag.objects.filter(is_active=True).values_list('tag', flat=True))
    return JsonResponse(dataset_tags, safe=False)


@login_required
def dataset_new_stepper_fa(request):
    return render(request, 'dataset/dataset_new_stepper.html', context={})


@login_required
def dataset_define_stepper_fa(request):
    return render(request, 'dataset/dataset_define_stepper.html', context={
        'direct_s3_uploads': settings.DIRECT_S3_UPLOADS,
        'direct_s3_upload_fallback': settings.DIRECT_S3_UPLOAD_FALLBACK,
    })


@login_required
def dataset_load_stepper_fa(request):
    return render(request, 'dataset/dataset_load_stepper.html', context={
        'direct_s3_uploads': settings.DIRECT_S3_UPLOADS,
        'direct_s3_upload_fallback': settings.DIRECT_S3_UPLOAD_FALLBACK,
    })


@login_required
@require_POST
def save_temp_metadata(request):
    """Create a draft dataset from JSON metadata and return a JSON response.

    The chunked upload endpoint is the normal workflow path. This endpoint is
    kept for clients that save metadata before uploading a file, but it must
    behave like an API instead of returning an HTML page for every request.
    """
    if not request.content_type.startswith('application/json'):
        return JsonResponse(
            {'status': 'error', 'message': 'Content-Type must be application/json'},
            status=415,
        )

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid JSON payload'},
            status=400,
        )

    metadata = payload.get('dataset') if isinstance(payload, dict) else None
    if not isinstance(metadata, dict):
        return JsonResponse(
            {'status': 'error', 'message': 'The dataset object is required'},
            status=400,
        )

    required_fields = ('dataset_name', 'dataset_owner', 'dataset_language', 'dataset_format')
    missing = [field for field in required_fields if not str(metadata.get(field, '')).strip()]
    if missing:
        return JsonResponse(
            {'status': 'error', 'message': 'Missing required fields', 'fields': missing},
            status=400,
        )

    tags_text = str(metadata.get('dataset_tags') or '')
    column_data = metadata.get('dataset_columnDataType') or {}
    if isinstance(column_data, str):
        try:
            column_data = json.loads(column_data)
        except json.JSONDecodeError:
            column_data = {}

    request_required = str(metadata.get('dataset_requestRequired') or 'No')
    if request_required not in {'Yes', 'No'}:
        request_required = 'No'

    new_dataset = Dataset.objects.create(
        user=request.user,
        name=str(metadata['dataset_name']).strip(),
        owner=str(metadata['dataset_owner']).strip(),
        language=str(metadata['dataset_language']).strip(),
        license=str(metadata.get('dataset_license') or ''),
        format=str(metadata['dataset_format']).strip(),
        recordsNum=str(metadata.get('dataset_recordsNum') or 0),
        price=metadata.get('dataset_price') or 0,
        requestRequired=request_required,
        desc=str(metadata.get('dataset_desc') or ''),
        dataset_tags=tags_text,
        columnDataType=column_data,
        datasetDate=timezone.now(),
        status='draft',
    )
    tags = [tag.strip() for tag in tags_text.split(',') if tag.strip()]
    if tags:
        new_dataset.tags.set(tags)

    return JsonResponse({
        'status': 'success',
        'dataset_id': new_dataset.pk,
        'detail_url': reverse('dataset:dataset_detail', args=[new_dataset.pk]),
    }, status=201)


# Backwards-compatible Python import and URL name for older clients.
saveTempMetaData = save_temp_metadata


###################################################
# S3 Client Configuration - FIXED VERSION
###################################################

def get_s3_client():
    """Initialize S3 client with workaround for XAmzContentSHA256Mismatch"""
    # Create a custom session to handle SSL issues
    session = boto3.Session()

    client = session.client(
        's3',
        endpoint_url=settings.CLOUD_STORAGE_CONFIG['S3_ENDPOINT'],
        aws_access_key_id=settings.CLOUD_STORAGE_CONFIG['ACCESS_KEY'],
        aws_secret_access_key=settings.CLOUD_STORAGE_CONFIG['SECRET_KEY'],
        region_name=settings.CLOUD_STORAGE_CONFIG.get('REGION', 'us-east-1'),
        config=Config(
            signature_version='s3v4',
            s3={'addressing_style': 'path'},
            retries={'max_attempts': 3, 'mode': 'standard'}
        ),
        verify=True
    )
    return client


def get_s3_resource():
    """Get S3 resource for alternative upload methods"""
    session = boto3.Session()
    return session.resource(
        's3',
        endpoint_url=settings.CLOUD_STORAGE_CONFIG['S3_ENDPOINT'],
        aws_access_key_id=settings.CLOUD_STORAGE_CONFIG['ACCESS_KEY'],
        aws_secret_access_key=settings.CLOUD_STORAGE_CONFIG['SECRET_KEY'],
        region_name=settings.CLOUD_STORAGE_CONFIG.get('REGION', 'us-east-1'),
        verify=True
    )


def create_user_bucket(user):
    """Create a bucket for the user"""
    s3_client = get_s3_client()
    bucket_name = get_user_bucket_name(user)

    try:
        s3_client.head_bucket(Bucket=bucket_name)
        return True, bucket_name
    except:
        try:
            # Simple bucket creation without complex configuration
            s3_client.create_bucket(Bucket=bucket_name)
            # Wait briefly for bucket to be ready
            import time
            time.sleep(1)
            return True, bucket_name
        except Exception as e:
            print(f"Bucket creation error: {str(e)}")
            return False, str(e)


def get_user_bucket_name(user):
    """Return one stable bucket per user so a batch has one storage home."""
    if not user or not user.username:
        raise ValueError("User must have a valid username")
    combined_string = f"{user.pk}:{user.username}".lower()
    combined_hash = hashlib.sha256(combined_string.encode()).hexdigest()[:16]
    bucket_name = f"user-{combined_hash}".lower()
    return bucket_name


def upload_to_user_bucket(file_path, bucket_name, file_name):
    """Upload file using multiple strategies to avoid XAmzContentSHA256Mismatch"""

    # Strategy 1: Try using requests directly (most reliable for MinIO)
    success, result = upload_via_requests(file_path, bucket_name, file_name)
    if success:
        return True, result

    # Strategy 2: Try using boto3 with different methods
    success, result = upload_via_boto3_multiple(file_path, bucket_name, file_name)
    if success:
        return True, result

    return False, "All upload strategies failed"


def upload_via_requests(file_path, bucket_name, file_name):
    """Upload using direct HTTP requests - most reliable for MinIO"""
    try:
        with open(file_path, 'rb') as f:
            # Generate a presigned URL and stream the file object.  Reading the
            # whole archive into RAM made large image datasets unsafe to upload.
            s3_client = get_s3_client()
            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params={'Bucket': bucket_name, 'Key': file_name, 'ContentType': get_content_type(file_name)},
                ExpiresIn=3600,
            )
            response = requests.put(
                presigned_url,
                data=f,
                headers={'Content-Type': get_content_type(file_name)},
                verify=True,
            )

        if response.status_code in [200, 204]:
            file_url = f"{settings.CLOUD_STORAGE_CONFIG['S3_ENDPOINT']}/{bucket_name}/{file_name}"
            return True, file_url
        else:
            return False, f"HTTP {response.status_code}: {response.text}"

    except Exception as e:
        return False, f"Requests upload failed: {str(e)}"


def upload_via_boto3_multiple(file_path, bucket_name, file_name):
    """Try multiple boto3 upload methods"""
    methods = [
        upload_via_boto3_put_object,
        upload_via_boto3_upload_fileobj,
        upload_via_boto3_resource
    ]

    for method in methods:
        success, result = method(file_path, bucket_name, file_name)
        if success:
            return True, result

    return False, "All boto3 methods failed"


def upload_via_boto3_put_object(file_path, bucket_name, file_name):
    """Upload using put_object with chunked reading"""
    try:
        s3_client = get_s3_client()

        # Read file in chunks to avoid memory issues
        with open(file_path, 'rb') as file_data:
            response = s3_client.put_object(
                Bucket=bucket_name,
                Key=file_name,
                Body=file_data,
                ContentType=get_content_type(file_name),
                ContentDisposition=f'attachment; filename="{file_name}"'
            )

        if response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 200:
            file_url = f"{settings.CLOUD_STORAGE_CONFIG['S3_ENDPOINT']}/{bucket_name}/{file_name}"
            return True, file_url
        else:
            return False, "PutObject failed"

    except Exception as e:
        return False, f"PutObject failed: {str(e)}"


def upload_via_boto3_upload_fileobj(file_path, bucket_name, file_name):
    """Upload using upload_fileobj"""
    try:
        s3_client = get_s3_client()

        with open(file_path, 'rb') as file_data:
            s3_client.upload_fileobj(
                file_data,
                bucket_name,
                file_name,
                ExtraArgs={
                    'ContentType': get_content_type(file_name),
                    'ContentDisposition': f'attachment; filename="{file_name}"'
                }
            )

        file_url = f"{settings.CLOUD_STORAGE_CONFIG['S3_ENDPOINT']}/{bucket_name}/{file_name}"
        return True, file_url

    except Exception as e:
        return False, f"UploadFileObj failed: {str(e)}"


def upload_via_boto3_resource(file_path, bucket_name, file_name):
    """Upload using S3 resource"""
    try:
        s3_resource = get_s3_resource()
        bucket = s3_resource.Bucket(bucket_name)

        with open(file_path, 'rb') as file_data:
            bucket.put_object(
                Key=file_name,
                Body=file_data,
                ContentType=get_content_type(file_name),
                ContentDisposition=f'attachment; filename="{file_name}"'
            )

        file_url = f"{settings.CLOUD_STORAGE_CONFIG['S3_ENDPOINT']}/{bucket_name}/{file_name}"
        return True, file_url

    except Exception as e:
        return False, f"S3 resource upload failed: {str(e)}"


def get_content_type(filename):
    """Determine content type based on file extension"""
    extension = os.path.splitext(filename)[1].lower()
    content_types = {
        '.csv': 'text/csv',
        '.txt': 'text/plain',
        '.json': 'application/json',
        '.parquet': 'application/octet-stream',
        '.zip': 'application/zip',
        '.gz': 'application/gzip',
        '.pdf': 'application/pdf',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
    }
    return content_types.get(extension, 'application/octet-stream')


def generate_presigned_url(bucket_name, object_key, expiration=3600):
    """Generate presigned URL for temporary access"""
    s3_client = get_s3_client()
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': object_key
            },
            ExpiresIn=expiration
        )
        return True, url
    except Exception as e:
        return False, str(e)



# Persistent upload sessions. Metadata and ownership live in PostgreSQL.
MAX_UPLOAD_CHUNKS = 10000
UPLOAD_SESSION_TTL = timedelta(hours=24)
MAX_UPLOAD_FILES = 1000
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024 * 1024  # 1 TiB logical batch limit
UPLOAD_PART_SIZE = 5 * 1024 * 1024


def validate_upload_id(upload_id):
    try:
        uuid.UUID(str(upload_id))
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def sanitize_filename(filename):
    filename = os.path.basename(filename)
    filename = filename.replace('\\', '_').replace('/', '_')
    for char in ['<', '>', ':', '"', '|', '?', '*']:
        filename = filename.replace(char, '_')
    return filename


def get_upload_session(upload_id, user, lock=False):
    if not validate_upload_id(upload_id):
        return None
    queryset = UploadSession.objects.filter(
        pk=upload_id,
        owner=user,
        status__in=[
            UploadSession.Status.CREATED,
            UploadSession.Status.UPLOADING,
        ],
    )
    if lock:
        queryset = queryset.select_for_update()
    session = queryset.first()
    if session and session.expires_at <= timezone.now():
        session.status = UploadSession.Status.EXPIRED
        session.save(update_fields=['status'])
        return None
    return session


def sanitize_relative_path(path, fallback=''):
    """Keep folder context while preventing traversal or absolute paths."""
    raw = str(path or fallback).replace('\\', '/').strip()
    parts = [part for part in raw.split('/') if part not in ('', '.', '..')]
    if not parts:
        return sanitize_filename(fallback)
    return '/'.join(sanitize_filename(part) for part in parts)


@login_required
@require_POST
def create_upload_batch(request):
    """Create one dataset/version envelope for a multi-file upload."""
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON payload'}, status=400)

    metadata = payload.get('metadata') or {}
    files = payload.get('files') or []
    if not isinstance(metadata, dict) or not isinstance(files, list):
        return JsonResponse({'status': 'error', 'message': 'Metadata and files are required'}, status=400)
    if not 1 <= len(files) <= MAX_UPLOAD_FILES:
        return JsonResponse({'status': 'error', 'message': f'Choose between 1 and {MAX_UPLOAD_FILES} files'}, status=400)
    name = str(metadata.get('dataset_name') or '').strip()
    if not name:
        return JsonResponse({'status': 'error', 'message': 'Dataset name is required'}, status=400)

    expected_bytes = 0
    manifest = []
    for item in files:
        if not isinstance(item, dict):
            return JsonResponse({'status': 'error', 'message': 'Invalid file manifest'}, status=400)
        try:
            size = int(item.get('size', 0))
        except (TypeError, ValueError):
            return JsonResponse({'status': 'error', 'message': 'Invalid file size'}, status=400)
        if size < 0:
            return JsonResponse({'status': 'error', 'message': 'Invalid file size'}, status=400)
        name_value = sanitize_filename(item.get('name', ''))
        relative_path = sanitize_relative_path(item.get('relative_path'), name_value)
        if not name_value:
            return JsonResponse({'status': 'error', 'message': 'Every file needs a name'}, status=400)
        expected_bytes += size
        manifest.append({'name': name_value, 'relative_path': relative_path, 'size': size})
    if expected_bytes > MAX_UPLOAD_BYTES:
        return JsonResponse({'status': 'error', 'message': 'The selected batch is too large'}, status=413)

    metadata = dict(metadata)
    metadata['dataset_name'] = name
    metadata['manifest'] = manifest
    metadata['dataset_requestRequired'] = 'Yes' if str(metadata.get('dataset_requestRequired')).lower() in ('yes', 'true', '1') else 'No'
    try:
        with transaction.atomic():
            dataset = Dataset.objects.create(
                user=request.user,
                code=f'pending-{uuid.uuid4().hex[:16]}',
                name=name,
                owner=metadata.get('dataset_owner', ''),
                language=metadata.get('dataset_language', ''),
                license=metadata.get('dataset_license', ''),
                format=metadata.get('dataset_format', ''),
                recordsNum=metadata.get('dataset_recordsNum', 0),
                price=metadata.get('dataset_price', 0) or 0,
                requestRequired=metadata['dataset_requestRequired'],
                desc=metadata.get('dataset_desc', ''),
                dataset_tags=metadata.get('dataset_tags', ''),
                columnDataType=metadata.get('dataset_columnDataType', []),
                filesCount=0,
                size='0 B',
                status='uploading',
            )
            if metadata.get('dataset_tags'):
                dataset.tags.set([tag.strip() for tag in str(metadata['dataset_tags']).split(',') if tag.strip()])
            version = DatasetVersion.objects.create(
                dataset=dataset,
                version=1,
                status=DatasetVersion.Status.DRAFT,
                pipeline_definition_version='standard-tabular:1.0.0',
                checksum_manifest={'manifest': manifest},
                created_by=request.user,
            )
            batch = UploadBatch.objects.create(
                owner=request.user,
                dataset=dataset,
                dataset_version=version,
                expected_files=len(manifest),
                expected_bytes=expected_bytes,
                metadata=metadata,
                expires_at=timezone.now() + UPLOAD_SESSION_TTL,
            )
    except (TypeError, ValueError, IntegrityError) as exc:
        return JsonResponse({'status': 'error', 'message': str(exc) or 'Could not create upload batch'}, status=400)
    return JsonResponse({
        'status': 'success',
        'batch_id': str(batch.id),
        'dataset_id': dataset.id,
        'dataset_version_id': version.id,
        'expected_files': batch.expected_files,
        'expected_bytes': batch.expected_bytes,
    })


@login_required
@require_POST
def update_upload_batch(request):
    """Save access/pricing choices collected after the file transfer stage."""
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON payload'}, status=400)
    batch_id = payload.get('batch_id')
    if not validate_upload_id(batch_id):
        return JsonResponse({'status': 'error', 'message': 'Invalid batch ID'}, status=400)
    batch = UploadBatch.objects.filter(pk=batch_id, owner=request.user).select_related('dataset').first()
    if batch is None or batch.status not in (UploadBatch.Status.PROCESSING, UploadBatch.Status.COMPLETED):
        return JsonResponse({'status': 'error', 'message': 'Upload batch is not ready for publication'}, status=409)
    metadata = dict(batch.metadata or {})
    metadata.update({
        'dataset_recordsNum': str(payload.get('dataset_recordsNum', metadata.get('dataset_recordsNum', '0'))),
        'dataset_price': str(payload.get('dataset_price', metadata.get('dataset_price', '0'))),
        'dataset_requestRequired': 'Yes' if str(payload.get('dataset_requestRequired', metadata.get('dataset_requestRequired', 'No'))).lower() in ('yes', 'true', '1') else 'No',
    })
    batch.metadata = metadata
    batch.save(update_fields=['metadata'])
    dataset = batch.dataset
    dataset.recordsNum = metadata['dataset_recordsNum']
    dataset.price = metadata['dataset_price'] or 0
    dataset.requestRequired = metadata['dataset_requestRequired']
    dataset.save(update_fields=['recordsNum', 'price', 'requestRequired'])
    return JsonResponse({'status': 'success', 'dataset_id': dataset.id})


def _batch_manifest_item(batch, relative_path, file_size):
    relative_path = sanitize_relative_path(relative_path)
    item = next(
        (entry for entry in (batch.metadata or {}).get('manifest', [])
         if entry.get('relative_path') == relative_path),
        None,
    )
    if item is None or int(item.get('size', -1)) != int(file_size):
        return None, relative_path
    return item, relative_path


def _batch_object_key(batch, file_name):
    return (
        f'datasets/{batch.dataset_id}/versions/{batch.dataset_version_id}/source/'
        f'{uuid.uuid4().hex}-{sanitize_filename(file_name)}'
    )


def _hash_s3_object(s3_client, bucket_name, object_key):
    digest = hashlib.sha256()
    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    body = response['Body']
    try:
        for chunk in iter(lambda: body.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    finally:
        body.close()
    return digest.hexdigest()


@login_required
@require_POST
def create_direct_upload(request):
    """Create an S3 multipart upload session for one batch file."""
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        batch_id = payload.get('batch_id')
        file_size = int(payload.get('file_size', 0))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Invalid upload metadata'}, status=400)
    if not validate_upload_id(batch_id) or file_size <= 0:
        return JsonResponse({'status': 'error', 'message': 'Invalid batch or file size'}, status=400)
    batch = UploadBatch.objects.filter(
        pk=batch_id,
        owner=request.user,
        status__in=[UploadBatch.Status.CREATED, UploadBatch.Status.UPLOADING],
    ).first()
    if batch is None or batch.expires_at <= timezone.now():
        return JsonResponse({'status': 'error', 'message': 'Invalid or expired upload batch'}, status=400)
    file_name = sanitize_filename(payload.get('file_name', ''))
    item, relative_path = _batch_manifest_item(batch, payload.get('relative_path') or file_name, file_size)
    if item is None or not file_name:
        return JsonResponse({'status': 'error', 'message': 'File does not match the upload manifest'}, status=400)
    bucket_ok, bucket_result = create_user_bucket(request.user)
    if not bucket_ok:
        return JsonResponse({'status': 'error', 'message': 'Bucket creation failed'}, status=500)
    object_key = _batch_object_key(batch, file_name)
    content_type = payload.get('content_type') or get_content_type(file_name)
    client = None
    multipart = None
    try:
        client = get_s3_client()
        multipart = client.create_multipart_upload(
            Bucket=bucket_result,
            Key=object_key,
            ContentType=content_type,
        )
        session = UploadSession.objects.create(
            owner=request.user,
            batch=batch,
            file_name=file_name,
            multipart_upload_id=multipart['UploadId'],
            storage_bucket=bucket_result,
            object_key=object_key,
            expected_size=file_size,
            total_chunks=math.ceil(file_size / UPLOAD_PART_SIZE),
            metadata={'relative_path': relative_path, 'original_name': file_name, 'content_type': content_type},
            status=UploadSession.Status.UPLOADING,
            expires_at=timezone.now() + UPLOAD_SESSION_TTL,
        )
        if batch.status == UploadBatch.Status.CREATED:
            batch.status = UploadBatch.Status.UPLOADING
            batch.save(update_fields=['status'])
    except Exception:
        if client is not None and multipart and multipart.get('UploadId'):
            try:
                client.abort_multipart_upload(
                    Bucket=bucket_result,
                    Key=object_key,
                    UploadId=multipart['UploadId'],
                )
            except Exception:
                logger.exception('Could not abort failed multipart creation for batch %s', batch_id)
        logger.exception('Could not create direct multipart upload for batch %s', batch_id)
        return JsonResponse({'status': 'error', 'message': 'Multipart upload could not start'}, status=502)
    return JsonResponse({
        'status': 'success',
        'upload_id': str(session.id),
        'multipart_upload_id': session.multipart_upload_id,
        'bucket': bucket_result,
        'object_key': object_key,
        'part_size': UPLOAD_PART_SIZE,
        'total_parts': session.total_chunks,
    })


@login_required
@require_POST
def direct_upload_part_url(request):
    """Return one short-lived presigned URL for a multipart part."""
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        upload_id = payload.get('upload_id')
        part_number = int(payload.get('part_number', 0))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Invalid part metadata'}, status=400)
    session = get_upload_session(upload_id, request.user)
    if session is None or not session.multipart_upload_id:
        return JsonResponse({'status': 'error', 'message': 'Invalid or expired multipart session'}, status=400)
    if part_number < 1 or part_number > session.total_chunks:
        return JsonResponse({'status': 'error', 'message': 'Invalid part number'}, status=400)
    try:
        url = get_s3_client().generate_presigned_url(
            'upload_part',
            Params={
                'Bucket': session.storage_bucket,
                'Key': session.object_key,
                'UploadId': session.multipart_upload_id,
                'PartNumber': part_number,
            },
            ExpiresIn=3600,
        )
    except Exception:
        logger.exception('Could not create multipart part URL for session %s', session.id)
        return JsonResponse({'status': 'error', 'message': 'Part URL could not be created'}, status=502)
    return JsonResponse({'status': 'success', 'url': url, 'part_number': part_number})


@login_required
@require_POST
def complete_direct_upload(request):
    """Complete an S3 multipart upload and register it in the dataset batch."""
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        upload_id = payload.get('upload_id')
        parts = payload.get('parts') or []
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid completion payload'}, status=400)
    if not validate_upload_id(upload_id) or not isinstance(parts, list):
        return JsonResponse({'status': 'error', 'message': 'Invalid completion metadata'}, status=400)
    with transaction.atomic():
        session = get_upload_session(upload_id, request.user, lock=True)
        if session is None or not session.multipart_upload_id:
            return JsonResponse({'status': 'error', 'message': 'Invalid or expired multipart session'}, status=400)
        expected = list(range(1, session.total_chunks + 1))
        normalized_parts = []
        try:
            for part in parts:
                normalized_parts.append({'PartNumber': int(part['part_number']), 'ETag': str(part['etag'])})
        except (KeyError, TypeError, ValueError):
            return JsonResponse({'status': 'error', 'message': 'Invalid part list'}, status=400)
        if sorted(item['PartNumber'] for item in normalized_parts) != expected or any(not item['ETag'] for item in normalized_parts):
            return JsonResponse({'status': 'error', 'message': 'All multipart parts are required'}, status=400)
        normalized_parts.sort(key=lambda item: item['PartNumber'])
        session.status = UploadSession.Status.ASSEMBLING
        session.save(update_fields=['status'])
    client = get_s3_client()
    try:
        client.complete_multipart_upload(
            Bucket=session.storage_bucket,
            Key=session.object_key,
            UploadId=session.multipart_upload_id,
            MultipartUpload={'Parts': normalized_parts},
        )
        head = client.head_object(Bucket=session.storage_bucket, Key=session.object_key)
        assembled_size = int(head.get('ContentLength', -1))
        if assembled_size != session.expected_size:
            raise ValueError('Multipart object size mismatch')
        source_sha256 = _hash_s3_object(client, session.storage_bucket, session.object_key)
        result = complete_batch_asset(
            session,
            request,
            session.storage_bucket,
            session.object_key,
            assembled_size,
            source_sha256,
        )
    except Exception:
        logger.exception('Could not complete direct multipart upload for session %s', session.id)
        try:
            client.abort_multipart_upload(Bucket=session.storage_bucket, Key=session.object_key, UploadId=session.multipart_upload_id)
        except Exception:
            try:
                client.delete_object(Bucket=session.storage_bucket, Key=session.object_key)
            except Exception:
                pass
        session.status = UploadSession.Status.FAILED
        session.save(update_fields=['status'])
        return JsonResponse({'status': 'error', 'message': 'Multipart completion failed'}, status=502)
    session.status = UploadSession.Status.COMPLETED
    session.completed_at = timezone.now()
    session.save(update_fields=['status', 'completed_at'])
    return JsonResponse({'status': 'success', **result})


@login_required
@require_POST
def abort_direct_upload(request):
    """Abort an incomplete browser multipart upload after a client-side failure."""
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        upload_id = payload.get('upload_id')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid abort payload'}, status=400)
    session = get_upload_session(upload_id, request.user, lock=True)
    if session is None or not session.multipart_upload_id:
        return JsonResponse({'status': 'success'})
    try:
        get_s3_client().abort_multipart_upload(
            Bucket=session.storage_bucket,
            Key=session.object_key,
            UploadId=session.multipart_upload_id,
        )
    except Exception:
        logger.exception('Could not abort direct multipart upload for session %s', session.id)
        return JsonResponse({'status': 'error', 'message': 'Multipart abort failed'}, status=502)
    session.status = UploadSession.Status.FAILED
    session.save(update_fields=['status'])
    return JsonResponse({'status': 'success'})


@login_required
@require_POST
def upload_dataset(request):
    if request.GET.get('finalize') == 'true':
        return finalize_upload(request)

    file_chunk = request.FILES.get('file')
    if not file_chunk:
        return JsonResponse(
            {'status': 'error', 'message': 'No file chunk received'},
            status=400,
        )

    try:
        chunk_number = int(request.POST.get('chunkNumber', 0))
        total_chunks = int(request.POST.get('totalChunks', 1))
        file_size = int(request.POST.get('fileSize', 0))
    except (TypeError, ValueError):
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid chunk metadata'},
            status=400,
        )

    if (
        total_chunks < 1
        or total_chunks > MAX_UPLOAD_CHUNKS
        or chunk_number < 0
        or chunk_number >= total_chunks
        or file_size < 0
    ):
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid chunk bounds'},
            status=400,
        )

    upload_id = request.POST.get('uploadId')
    file_name = sanitize_filename(request.POST.get('fileName', ''))
    batch = None
    batch_id = request.POST.get('batchId')

    if chunk_number == 0:
        if not file_name:
            return JsonResponse(
                {'status': 'error', 'message': 'Filename required'},
                status=400,
            )
        try:
            metadata = json.loads(request.POST.get('metadata', '{}'))
        except json.JSONDecodeError:
            return JsonResponse(
                {'status': 'error', 'message': 'Invalid metadata format'},
                status=400,
            )
        if not isinstance(metadata, dict):
            return JsonResponse(
                {'status': 'error', 'message': 'Metadata must be an object'},
                status=400,
            )
        if batch_id:
            if not validate_upload_id(batch_id):
                return JsonResponse({'status': 'error', 'message': 'Invalid batch ID'}, status=400)
            batch = UploadBatch.objects.filter(
                pk=batch_id,
                owner=request.user,
                status__in=[UploadBatch.Status.CREATED, UploadBatch.Status.UPLOADING],
            ).first()
            if batch is None or batch.expires_at <= timezone.now():
                return JsonResponse({'status': 'error', 'message': 'Invalid or expired upload batch'}, status=400)
            relative_path = sanitize_relative_path(request.POST.get('relativePath'), file_name)
            manifest_item = next(
                (item for item in (batch.metadata or {}).get('manifest', [])
                 if item.get('relative_path') == relative_path),
                None,
            )
            if manifest_item is None or int(manifest_item.get('size', -1)) != file_size:
                return JsonResponse({'status': 'error', 'message': 'File does not match the upload manifest'}, status=400)
            metadata.setdefault('relative_path', relative_path)
            metadata.setdefault('original_name', file_name)
        session = UploadSession.objects.create(
            owner=request.user,
            batch=batch,
            file_name=file_name,
            expected_size=file_size,
            total_chunks=total_chunks,
            metadata=metadata,
            status=UploadSession.Status.UPLOADING,
            expires_at=timezone.now() + UPLOAD_SESSION_TTL,
        )
        upload_id = str(session.pk)
        if batch is not None and batch.status == UploadBatch.Status.CREATED:
            batch.status = UploadBatch.Status.UPLOADING
            batch.save(update_fields=['status'])
    else:
        session = get_upload_session(upload_id, request.user)
        if session is None:
            return JsonResponse(
                {'status': 'error', 'message': 'Invalid or expired upload ID'},
                status=400,
            )
        if session.total_chunks != total_chunks:
            return JsonResponse(
                {'status': 'error', 'message': 'Chunk count does not match upload session'},
                status=400,
            )
        if batch_id and str(session.batch_id) != str(batch_id):
            return JsonResponse({'status': 'error', 'message': 'Batch does not match upload session'}, status=400)

    if session is None:
        session = get_upload_session(upload_id, request.user)
    if session is None:
        return JsonResponse(
            {'status': 'error', 'message': 'Invalid or expired upload ID'},
            status=400,
        )

    if UploadPart.objects.filter(
        upload_session=session,
        chunk_number=chunk_number,
    ).exists():
        return JsonResponse(
            {'status': 'error', 'message': 'Duplicate chunk'},
            status=400,
        )

    chunk_path = f"uploads/temp/{session.pk}/chunk_{chunk_number}"
    try:
        saved_path = default_storage.save(
            chunk_path,
            ContentFile(file_chunk.read()),
        )
        try:
            UploadPart.objects.create(
                upload_session=session,
                chunk_number=chunk_number,
                storage_path=saved_path,
                byte_size=file_chunk.size,
            )
        except IntegrityError:
            if default_storage.exists(saved_path):
                default_storage.delete(saved_path)
            return JsonResponse(
                {'status': 'error', 'message': 'Duplicate chunk'},
                status=400,
            )
    except Exception:
        return JsonResponse(
            {'status': 'error', 'message': 'Chunk save failed'},
            status=500,
        )

    received_chunks = list(
        session.parts.order_by('chunk_number').values_list(
            'chunk_number',
            flat=True,
        )
    )
    return JsonResponse({
        'status': 'success',
        'upload_id': str(session.pk),
        'received_chunks': received_chunks,
    })


def complete_batch_asset(upload_info, request, bucket_name, object_key, assembled_size, source_sha256):
    """Persist one asset and finish the dataset pipeline when the batch is complete."""
    batch = upload_info.batch
    with transaction.atomic():
        batch = UploadBatch.objects.select_for_update().select_related(
            'dataset', 'dataset_version'
        ).get(pk=batch.pk, owner=request.user)
        if batch.status in (UploadBatch.Status.COMPLETED, UploadBatch.Status.PROCESSING):
            raise ValidationError('Upload batch is already complete')
        metadata = dict(batch.metadata or {})
        links = list(batch.dataset.downloadLink or [])
        version_manifest = dict(batch.dataset_version.checksum_manifest or {})
        privacy_plan = metadata.get('privacy_plan')
        if isinstance(privacy_plan, dict):
            # Keep the exact client transformation receipt with the immutable
            # version. The worker still validates the uploaded artifact before
            # publication; this is provenance, not a trust boundary.
            version_manifest['privacy_plan'] = privacy_plan
            batch.dataset_version.checksum_manifest = version_manifest
            batch.dataset_version.save(update_fields=['checksum_manifest'])
        link = {
            'url': '',
            'bucket_name': bucket_name,
            'object_key': object_key,
            'relative_path': upload_info.metadata.get('relative_path', upload_info.file_name),
            'size': assembled_size,
            'size_human': sizeof_fmt(assembled_size),
            'privacy_applied': bool(privacy_plan),
        }
        DatasetAsset.objects.create(
            dataset_version=batch.dataset_version,
            kind=DatasetAsset.Kind.SOURCE,
            object_key=object_key,
            storage_bucket=bucket_name,
            original_name=upload_info.file_name,
            relative_path=link['relative_path'],
            media_type=get_content_type(upload_info.file_name),
            byte_size=assembled_size,
            sha256=source_sha256,
            status='quarantined',
        )
        links.append(link)
        completed_files = batch.completed_files + 1
        completed_bytes = batch.completed_bytes + assembled_size
        all_uploaded = completed_files >= batch.expected_files
        batch.completed_files = completed_files
        batch.completed_bytes = completed_bytes
        batch.status = UploadBatch.Status.PROCESSING if all_uploaded else UploadBatch.Status.UPLOADING
        if all_uploaded:
            batch.completed_at = timezone.now()
        batch.save(update_fields=['completed_files', 'completed_bytes', 'status', 'completed_at'])

        dataset = batch.dataset
        dataset.filesCount = completed_files
        dataset.size = sizeof_fmt(completed_bytes)
        dataset.downloadLink = links
        dataset.code = bucket_name
        dataset.status = 'quarantined' if all_uploaded else 'uploading'
        dataset.save(update_fields=['filesCount', 'size', 'downloadLink', 'code', 'status'])

        pipeline_run = None
        if all_uploaded:
            has_privacy_plan = isinstance(metadata.get('privacy_plan'), dict)
            pipeline_name = 'standard-tabular-privacy' if has_privacy_plan else 'standard-tabular'
            if batch.dataset_version.pipeline_definition_version != f'{pipeline_name}:1.0.0':
                batch.dataset_version.pipeline_definition_version = f'{pipeline_name}:1.0.0'
                batch.dataset_version.save(update_fields=['pipeline_definition_version'])
            pipeline_definition, _ = PipelineDefinition.objects.update_or_create(
                name=pipeline_name,
                version='1.0.0',
                defaults={'definition': {'steps': ['checksum', 'privacy_receipt', 'quality'] if has_privacy_plan else ['checksum', 'quality']}, 'is_active': True},
            )
            pipeline_run, _ = enqueue_pipeline(
                batch.dataset_version.id,
                pipeline_definition.id,
                requested_by=request.user,
            )
    return {
        'download_link': link,
        'dataset_id': batch.dataset_id,
        'dataset_version_id': batch.dataset_version_id,
        'batch_id': str(batch.id),
        'completed_files': completed_files,
        'expected_files': batch.expected_files,
        'completed_bytes': completed_bytes,
        'batch_complete': all_uploaded,
        'pipeline_run_id': pipeline_run.id if pipeline_run else None,
        'pipeline_status': pipeline_run.status if pipeline_run else None,
        'metadata': metadata,
    }


def finalize_upload(request):
    upload_id = request.GET.get('uploadId')
    if not validate_upload_id(upload_id):
        return JsonResponse({
            'status': 'error',
            'message': 'Invalid upload ID',
            'code': 'INVALID_UPLOAD_ID',
        }, status=400)

    with transaction.atomic():
        upload_info = get_upload_session(upload_id, request.user, lock=True)
        if upload_info is None:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid or expired upload ID',
                'code': 'INVALID_UPLOAD_ID',
            }, status=400)

        expected_chunks = set(range(upload_info.total_chunks))
        received_chunks = set(
            upload_info.parts.values_list('chunk_number', flat=True)
        )
        if received_chunks != expected_chunks:
            missing = sorted(expected_chunks - received_chunks)
            cleanup_upload(upload_id, status=UploadSession.Status.FAILED)
            return JsonResponse({
                'status': 'error',
                'message': f'Missing chunks: {missing}',
                'code': 'MISSING_CHUNKS',
            }, status=400)

        upload_info.status = UploadSession.Status.ASSEMBLING
        upload_info.save(update_fields=['status'])

    final_dir = os.path.join(
        'uploads',
        timezone.now().strftime('%Y'),
        timezone.now().strftime('%m'),
        timezone.now().strftime('%d'),
    )
    final_path = os.path.join(final_dir, upload_info.file_name)

    try:
        os.makedirs(
            os.path.dirname(default_storage.path(final_path)),
            exist_ok=True,
        )
        with open(default_storage.path(final_path), 'wb') as final_file:
            for part in upload_info.parts.order_by('chunk_number'):
                with open(default_storage.path(part.storage_path), 'rb') as chunk_file:
                    final_file.write(chunk_file.read())
    except Exception:
        cleanup_upload(upload_id, status=UploadSession.Status.FAILED)
        return JsonResponse({
            'status': 'error',
            'message': 'File assembly failed',
            'code': 'FILE_ASSEMBLY_FAILED',
        }, status=500)

    assembled_path = default_storage.path(final_path)
    if not os.path.exists(assembled_path):
        cleanup_upload(upload_id, status=UploadSession.Status.FAILED)
        return JsonResponse({
            'status': 'error',
            'message': 'Assembled file not found',
            'code': 'FILE_NOT_FOUND',
        }, status=500)

    assembled_size = os.path.getsize(assembled_path)
    if assembled_size != upload_info.expected_size:
        cleanup_upload(upload_id, status=UploadSession.Status.FAILED)
        if os.path.exists(assembled_path):
            os.remove(assembled_path)
        return JsonResponse({
            'status': 'error',
            'message': 'File size mismatch',
            'code': 'FILE_SIZE_MISMATCH',
        }, status=400)

    source_sha256 = file_sha256(assembled_path)
    bucket_success, bucket_result = create_user_bucket(request.user)
    if not bucket_success:
        cleanup_upload(upload_id, status=UploadSession.Status.FAILED)
        if os.path.exists(assembled_path):
            os.remove(assembled_path)
        return JsonResponse({
            'status': 'error',
            'message': 'Bucket creation failed',
            'code': 'BUCKET_CREATION_FAILED',
        }, status=500)

    object_key = upload_info.file_name
    if upload_info.batch_id:
        object_key = (
            f'datasets/{upload_info.batch.dataset_id}/versions/'
            f'{upload_info.batch.dataset_version_id}/source/'
            f'{uuid.uuid4().hex}-{upload_info.file_name}'
        )
    upload_success, upload_result = upload_to_user_bucket(
        assembled_path,
        bucket_result,
        object_key,
    )
    if not upload_success:
        cleanup_upload(upload_id, status=UploadSession.Status.FAILED)
        if os.path.exists(assembled_path):
            os.remove(assembled_path)
        return JsonResponse({
            'status': 'error',
            'message': 'Cloud upload failed',
            'code': 'CLOUD_UPLOAD_FAILED',
        }, status=500)

    if upload_info.batch_id:
        try:
            result = complete_batch_asset(
                upload_info,
                request,
                bucket_result,
                object_key,
                assembled_size,
                source_sha256,
            )
        except ValidationError as exc:
            cleanup_upload(upload_id, status=UploadSession.Status.FAILED)
            if os.path.exists(assembled_path):
                os.remove(assembled_path)
            return JsonResponse({'status': 'error', 'message': str(exc)}, status=409)
        except Exception:
            cleanup_upload(upload_id, status=UploadSession.Status.FAILED)
            if os.path.exists(assembled_path):
                os.remove(assembled_path)
            return JsonResponse({'status': 'error', 'message': 'Database error', 'code': 'DATABASE_ERROR'}, status=500)
        upload_info.status = UploadSession.Status.COMPLETED
        upload_info.completed_at = timezone.now()
        upload_info.save(update_fields=['status', 'completed_at'])
        cleanup_upload(upload_id)
        if os.path.exists(assembled_path):
            os.remove(assembled_path)
        return JsonResponse({'status': 'success', **result})

    download_link = {
        'url': '',
        'bucket_name': bucket_result,
        'object_key': object_key,
        'size': upload_info.expected_size,
        'size_human': sizeof_fmt(upload_info.expected_size),
    }

    try:
        with transaction.atomic():
            metadata = upload_info.metadata
            dataset = Dataset.objects.create(
                user=request.user,
                code=bucket_result,
                name=metadata.get('dataset_name', ''),
                owner=metadata.get('dataset_owner', ''),
                language=metadata.get('dataset_language', ''),
                license=metadata.get('dataset_license', ''),
                format=metadata.get('dataset_format', ''),
                recordsNum=metadata.get('dataset_recordsNum', 0),
                price=metadata.get('dataset_price', 0),
                requestRequired=metadata.get('dataset_requestRequired', False),
                desc=metadata.get('dataset_desc', ''),
                dataset_tags=metadata.get('dataset_tags', ''),
                columnDataType=metadata.get('dataset_columnDataType', ''),
                downloadLink=[download_link],
                filesCount=1,
                size=upload_info.expected_size,
                status='quarantined',
            )
            if metadata.get('dataset_tags'):
                tags = [
                    tag.strip()
                    for tag in metadata['dataset_tags'].split(',')
                    if tag.strip()
                ]
                dataset.tags.set(tags)
            version = DatasetVersion.objects.create(
                dataset=dataset,
                version=1,
                status=DatasetVersion.Status.DRAFT,
                pipeline_definition_version='standard-tabular:1.0.0',
                checksum_manifest={
                    'source_sha256': source_sha256,
                    'source_size': assembled_size,
                },
                created_by=request.user,
            )
            DatasetAsset.objects.create(
                dataset_version=version,
                kind=DatasetAsset.Kind.SOURCE,
                object_key=upload_info.file_name,
                storage_bucket=bucket_result,
                original_name=upload_info.file_name,
                media_type=get_content_type(upload_info.file_name),
                byte_size=assembled_size,
                sha256=source_sha256,
                status='quarantined',
            )
            pipeline_definition, _ = PipelineDefinition.objects.update_or_create(
                name='standard-tabular',
                version='1.0.0',
                defaults={
                    'definition': {
                        'steps': ['checksum', 'quality'],
                    },
                    'is_active': True,
                },
            )
            pipeline_run, _ = enqueue_pipeline(
                version.id,
                pipeline_definition.id,
                requested_by=request.user,
            )
    except Exception:
        cleanup_upload(upload_id, status=UploadSession.Status.FAILED)
        if os.path.exists(assembled_path):
            os.remove(assembled_path)
        return JsonResponse({
            'status': 'error',
            'message': 'Database error',
            'code': 'DATABASE_ERROR',
        }, status=500)

    upload_info.status = UploadSession.Status.COMPLETED
    upload_info.completed_at = timezone.now()
    upload_info.save(update_fields=['status', 'completed_at'])
    cleanup_upload(upload_id)
    if os.path.exists(assembled_path):
        os.remove(assembled_path)

    return JsonResponse({
        'status': 'success',
        'download_link': download_link,
        'dataset_id': dataset.id,
        'metadata': metadata,
        'bucket': bucket_result,
        'dataset_version_id': version.id,
        'pipeline_run_id': pipeline_run.id,
        'pipeline_status': pipeline_run.status,
    })


def cleanup_upload(upload_id, status=None):
    session = UploadSession.objects.filter(pk=upload_id).first()
    if session is None:
        return
    # Native multipart uploads have no UploadPart rows. Abort them explicitly
    # when a session expires or fails so incomplete object-store parts do not
    # accumulate until the bucket lifecycle rule runs.
    if session.multipart_upload_id and session.storage_bucket and session.object_key:
        try:
            get_s3_client().abort_multipart_upload(
                Bucket=session.storage_bucket,
                Key=session.object_key,
                UploadId=session.multipart_upload_id,
            )
        except Exception:
            # Cleanup is best-effort; the scheduled object-store lifecycle
            # policy remains the final safety net.
            pass
    for part in session.parts.all():
        if default_storage.exists(part.storage_path):
            default_storage.delete(part.storage_path)
    session.parts.all().delete()
    if status is not None:
        session.status = status
        session.save(update_fields=['status'])

def file_sha256(file_path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(file_path, 'rb') as file_data:
        for chunk in iter(lambda: file_data.read(chunk_size), b''):
            digest.update(chunk)
    return digest.hexdigest()


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Y', suffix)


# Rest of the code remains the same for Dataset Viewer, Annotation, etc.
# [Include the Dataset Viewer, Annotation, and other functions from your original code]

###################################################
# Dataset Viewer
###################################################
import requests
import tempfile
import os
import pandas as pd
import math
from django.views.generic import TemplateView
from django.utils.safestring import mark_safe
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.conf import settings
import pygwalker as pyg
from .models import Dataset


class MyPygWalkerView1(TemplateView):
    template_name = "dataset/dataset_viewer.html"

    def get_context_data(self, **kwargs):
        dataset = get_object_or_404(Dataset, id=self.request.GET.get('dataset_id'))
        if not can_access_dataset(self.request.user, dataset):
            raise PermissionDenied
        return super().get_context_data(**kwargs)

    def get_download_info(self, download_links, file_index=0):
        """Extract file info from dataset's downloadLink by index"""
        try:
            if download_links and isinstance(download_links, list) and file_index < len(download_links):
                return download_links[file_index]
            return None
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error parsing downloadLink: {str(e)}")
            return None

    def download_file_from_s3(self, bucket_name, object_key):
        """Download file from S3 using presigned URL and return temporary file path"""
        try:
            # Generate fresh presigned URL
            success, presigned_url = generate_presigned_url(bucket_name, object_key, 3600)
            if not success:
                print(f"Failed to generate presigned URL for {bucket_name}/{object_key}")
                return None

            # Download using requests from the presigned URL
            response = requests.get(presigned_url, stream=True, timeout=30)
            response.raise_for_status()

            # Extract file extension
            file_ext = object_key.split('.')[-1].lower() if '.' in object_key else 'bin'

            print(f"Downloading file from S3: {object_key}")

            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp_file.write(chunk)
                return tmp_file.name

        except requests.exceptions.RequestException as e:
            print(f"Error downloading file from S3: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error during download: {str(e)}")
            return None

    def get_pygwalker_config(self):
        """Returns a config to show ONLY the data tab"""
        return {
            "config": {
                "menu": {
                    "data": True,
                    "visualize": False,
                    "export": False,
                    "help": False
                },
                "header": {
                    "title": "Data Viewer",
                    "show": True
                },
                "themeKey": "vega",
                "themeConfig": {
                    "currentTheme": "light",
                    "themeSet": "light"
                },
                "showCloudTool": False,
                "enableExportData": False,
                "enableExportImage": False
            }
        }

    def read_data_file(self, file_path):
        """Read data file (CSV or Parquet) into DataFrame"""
        file_ext = file_path.split('.')[-1].lower()
        try:
            if file_ext == 'parquet':
                return pd.read_parquet(file_path)
            elif file_ext == 'xlsx' or file_ext == 'xls':
                return pd.read_excel(file_path)
            elif file_ext == 'json':
                return pd.read_json(file_path)
            else:  # default to CSV
                return pd.read_csv(file_path)
        except Exception as e:
            print(f"Error reading file {file_path}: {str(e)}")
            return pd.DataFrame()

    def sample_dataframe(self, df):
        """Take 10% sample of dataframe (max 100 rows)"""
        if df.empty:
            return df

        sample_size = min(100, max(1, math.ceil(len(df) * 0.1)))
        return df.sample(n=sample_size, random_state=42)

    def get_file_info_list(self, download_links):
        """Get list of file information for navigation"""
        file_list = []
        if download_links and isinstance(download_links, list):
            for index, file_info in enumerate(download_links):
                object_key = file_info.get('object_key', '')
                extension = object_key.split('.')[-1].lower() if '.' in object_key else 'unknown'
                file_list.append({
                    'index': index,
                    'filename': object_key.split('/')[-1],
                    'object_key': object_key,
                    'size': file_info.get('size', 0),
                    'size_human': file_info.get('size_human', '0 B'),
                    'bucket_name': file_info.get('bucket_name', ''),
                    'extension': extension
                })
        return file_list

    def get_supported_extensions(self):
        """Return list of supported file extensions"""
        return ['csv', 'parquet', 'xlsx', 'xls', 'json']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dataset_id = self.request.GET.get('dataset_id')
        file_index = int(self.request.GET.get('file_index', -1))  # Default to -1 (no file selected)

        if not dataset_id:
            context['error'] = "No dataset ID provided"
            return context

        try:
            dataset = Dataset.objects.get(id=dataset_id)
            context['dataset'] = dataset

            # Get download links info (contains bucket_name and object_key)
            download_links = dataset.downloadLink
            context['file_count'] = len(download_links) if download_links else 0
            context['current_file_index'] = file_index

            # Get file list for navigation
            context['file_list'] = self.get_file_info_list(download_links)
            context['supported_extensions'] = self.get_supported_extensions()

            if not download_links:
                context['error'] = "No files available for this dataset"
                return context

            # Only process file data if a file is selected
            if file_index >= 0 and file_index < len(download_links):
                # Get specific file info by index
                file_info = self.get_download_info(download_links, file_index)
                if not file_info:
                    context['error'] = f"File index {file_index} not found"
                    return context

                bucket_name = file_info.get('bucket_name')
                object_key = file_info.get('object_key')

                if not bucket_name or not object_key:
                    context['error'] = "Missing bucket name or object key"
                    return context

                # Check if file format is supported
                file_extension = object_key.split('.')[-1].lower() if '.' in object_key else ''
                supported_extensions = self.get_supported_extensions()

                if file_extension not in supported_extensions:
                    context[
                        'error'] = f"File format '{file_extension}' is not supported for viewing. Supported formats: {', '.join(supported_extensions)}"
                    context['current_filename'] = object_key.split('/')[-1]
                    context['current_file_extension'] = file_extension
                    return context

                # Download the file using bucket_name and object_key
                tmp_file_path = self.download_file_from_s3(bucket_name, object_key)
                if not tmp_file_path:
                    context['error'] = "Could not download file from S3"
                    return context

                # Read the downloaded file
                df = self.read_data_file(tmp_file_path)

                # Clean up temporary file
                try:
                    os.unlink(tmp_file_path)
                except Exception as e:
                    print(f"Error cleaning up temp file: {e}")

                if df.empty:
                    context['error'] = "Could not load dataset or dataset is empty"
                    context['current_filename'] = object_key.split('/')[-1]
                else:
                    sampled_df = self.sample_dataframe(df)
                    pyg_html = pyg.walk(
                        sampled_df,
                        spec=self.get_pygwalker_config(),
                        return_html=True
                    )
                    context['pygwalker_html'] = mark_safe(pyg_html)
                    context['row_count'] = len(df)
                    context['sample_count'] = len(sampled_df)
                    context['current_filename'] = object_key.split('/')[-1]
                    context['current_file_extension'] = file_extension
                    context['columns_count'] = len(df.columns)
                    context['columns_list'] = list(df.columns)

        except Dataset.DoesNotExist:
            context['error'] = "Dataset not found"
        except PermissionDenied:
            raise
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            context['error'] = f"An unexpected error occurred: {str(e)}"

        return context


class MyPygWalkerView(TemplateView):
    template_name = "dataset/dataset_viewer.html"

    def get_context_data(self, **kwargs):
        dataset = get_object_or_404(Dataset, id=self.request.GET.get('dataset_id'))
        if not can_access_dataset(self.request.user, dataset):
            raise PermissionDenied
        return super().get_context_data(**kwargs)

    def get_download_info(self, download_links, file_index=0):
        """Extract file info from dataset's downloadLink by index"""
        try:
            if download_links and isinstance(download_links, list) and file_index < len(download_links):
                return download_links[file_index]
            return None
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error parsing downloadLink: {str(e)}")
            return None

    def download_file_from_s3(self, bucket_name, object_key):
        """Download file from S3 using presigned URL and return temporary file path"""
        try:
            # Generate fresh presigned URL
            success, presigned_url = generate_presigned_url(bucket_name, object_key, 3600)
            if not success:
                print(f"Failed to generate presigned URL for {bucket_name}/{object_key}")
                return None

            # Download using requests from the presigned URL
            response = requests.get(presigned_url, stream=True, timeout=30)
            response.raise_for_status()

            # Extract file extension
            file_ext = object_key.split('.')[-1].lower() if '.' in object_key else 'bin'

            print(f"Downloading file from S3: {object_key}")

            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp_file.write(chunk)
                return tmp_file.name

        except requests.exceptions.RequestException as e:
            print(f"Error downloading file from S3: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error during download: {str(e)}")
            return None

    def get_pygwalker_config(self):
        """Returns a config to show ONLY the data tab"""
        return {
            "config": {
                "menu": {
                    "data": True,
                    "visualize": False,
                    "export": False,
                    "help": False
                },
                "header": {
                    "title": "Data Viewer",
                    "show": True
                },
                "themeKey": "vega",
                "themeConfig": {
                    "currentTheme": "light",
                    "themeSet": "light"
                },
                "showCloudTool": False,
                "enableExportData": False,
                "enableExportImage": False
            }
        }

    def read_data_file(self, file_path):
        """Read data file (CSV or Parquet) into DataFrame"""
        file_ext = file_path.split('.')[-1].lower()
        try:
            if file_ext == 'parquet':
                return pd.read_parquet(file_path)
            elif file_ext == 'xlsx' or file_ext == 'xls':
                return pd.read_excel(file_path)
            elif file_ext == 'json':
                return pd.read_json(file_path)
            else:  # default to CSV
                return pd.read_csv(file_path)
        except Exception as e:
            print(f"Error reading file {file_path}: {str(e)}")
            return pd.DataFrame()

    def sample_dataframe(self, df):
        """Take 10% sample of dataframe (max 100 rows)"""
        if df.empty:
            return df

        sample_size = min(100, max(1, math.ceil(len(df) * 0.1)))
        return df.sample(n=sample_size, random_state=42)

    def get_file_info_list(self, download_links):
        """Get list of file information for navigation"""
        file_list = []
        if download_links and isinstance(download_links, list):
            for index, file_info in enumerate(download_links):
                object_key = file_info.get('object_key', '')
                extension = object_key.split('.')[-1].lower() if '.' in object_key else 'unknown'
                file_list.append({
                    'index': index,
                    'filename': object_key.split('/')[-1],
                    'object_key': object_key,
                    'size': file_info.get('size', 0),
                    'size_human': file_info.get('size_human', '0 B'),
                    'bucket_name': file_info.get('bucket_name', ''),
                    'extension': extension
                })
        return file_list

    def get_supported_extensions(self):
        """Return list of supported file extensions"""
        return ['csv', 'parquet', 'xlsx', 'xls', 'json']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dataset_id = self.request.GET.get('dataset_id')
        file_index = int(self.request.GET.get('file_index', -1))

        if not dataset_id:
            context['error'] = "No dataset ID provided"
            return context

        try:
            dataset = Dataset.objects.get(id=dataset_id)
            context['dataset'] = dataset

            # Get download links info
            download_links = dataset.downloadLink
            context['file_count'] = len(download_links) if download_links else 0
            context['current_file_index'] = file_index

            # Get file list for navigation
            context['file_list'] = self.get_file_info_list(download_links)
            context['supported_extensions'] = self.get_supported_extensions()

            if not download_links:
                context['error'] = "No files available for this dataset"
                return context

            # Only process file data if a file is selected
            if file_index >= 0 and file_index < len(download_links):
                # Get specific file info by index
                file_info = self.get_download_info(download_links, file_index)
                if not file_info:
                    context['error'] = f"File index {file_index} not found"
                    return context

                bucket_name = file_info.get('bucket_name')
                object_key = file_info.get('object_key')

                if not bucket_name or not object_key:
                    context['error'] = "Missing bucket name or object key"
                    return context

                # Store current file info for template
                context['current_file_info'] = file_info
                context['current_filename'] = object_key.split('/')[-1]
                context['current_file_extension'] = object_key.split('.')[-1].lower() if '.' in object_key else ''

                # Check if file format is supported
                supported_extensions = self.get_supported_extensions()
                if context['current_file_extension'] not in supported_extensions:
                    context[
                        'error'] = f"File format '{context['current_file_extension']}' is not supported for viewing. Supported formats: {', '.join(supported_extensions)}"
                    return context

                # Download the file using bucket_name and object_key
                tmp_file_path = self.download_file_from_s3(bucket_name, object_key)
                if not tmp_file_path:
                    context['error'] = "Could not download file from S3"
                    return context

                # Read the downloaded file
                df = self.read_data_file(tmp_file_path)

                # Clean up temporary file
                try:
                    os.unlink(tmp_file_path)
                except Exception as e:
                    print(f"Error cleaning up temp file: {e}")

                if df.empty:
                    context['error'] = "Could not load dataset or dataset is empty"
                else:
                    sampled_df = self.sample_dataframe(df)
                    pyg_html = pyg.walk(
                        sampled_df,
                        spec=self.get_pygwalker_config(),
                        return_html=True
                    ).to_html()
                    context['pygwalker_html'] = mark_safe(pyg_html)
                    context['row_count'] = len(df)
                    context['sample_count'] = len(sampled_df)
                    context['columns_count'] = len(df.columns)
                    context['columns_list'] = list(df.columns)

        except Dataset.DoesNotExist:
            context['error'] = "Dataset not found"
        except PermissionDenied:
            raise
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            context['error'] = f"An unexpected error occurred: {str(e)}"

        return context


from django.shortcuts import render, get_object_or_404


def dataset_files_fa(request, pk=None):
    dataset_id = pk or request.GET.get('dataset_id')

    if not dataset_id:
        return render(request, 'dataset/dataset_files.html', {'error': 'No dataset ID provided'})

    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)
        if not can_access_dataset(request.user, dataset):
            raise PermissionDenied

        # Get download links info
        download_links = dataset.downloadLink
        file_count = len(download_links) if download_links else 0

        # Get file list for navigation
        file_list = []
        if download_links and isinstance(download_links, list):
            for index, file_info in enumerate(download_links):
                object_key = file_info.get('object_key', '')
                extension = object_key.split('.')[-1].lower() if '.' in object_key else 'unknown'
                file_list.append({
                    'index': index,
                    'filename': object_key.split('/')[-1],
                    'object_key': object_key,
                    'size': file_info.get('size', 0),
                    'size_human': file_info.get('size_human', '0 B'),
                    'bucket_name': file_info.get('bucket_name', ''),
                    'extension': extension
                })

        # Supported extensions for display
        supported_extensions = ['csv', 'parquet', 'xlsx', 'xls', 'json']

        context = {
            'dataset': dataset,
            'file_list': file_list,
            'file_count': file_count,
            'supported_extensions': supported_extensions,
        }

        # Check if a file is selected for preview
        file_index = request.GET.get('file_index')
        if file_index:
            try:
                file_index = int(file_index)
                if file_index >= 0 and file_index < len(download_links):
                    # Use MyPygWalkerView methods to get file preview
                    viewer = MyPygWalkerView()

                    # Get file info
                    file_info = viewer.get_download_info(download_links, file_index)
                    if file_info:
                        context['current_file_index'] = file_index
                        context['current_file_info'] = file_info
                        context['current_filename'] = file_info.get('object_key', '').split('/')[-1]
                        context['current_file_extension'] = file_info.get('object_key', '').split('.')[
                            -1].lower() if '.' in file_info.get('object_key', '') else ''

                        # Only load PygWalker data if file format is supported
                        if context['current_file_extension'] in supported_extensions:
                            # Download and process the file
                            bucket_name = file_info.get('bucket_name')
                            object_key = file_info.get('object_key')

                            if bucket_name and object_key:
                                tmp_file_path = viewer.download_file_from_s3(bucket_name, object_key)
                                if tmp_file_path:
                                    df = viewer.read_data_file(tmp_file_path)

                                    if not df.empty:
                                        sampled_df = viewer.sample_dataframe(df)
                                        pyg_html = pyg.walk(
                                            sampled_df,
                                            spec=viewer.get_pygwalker_config(),
                                            return_html=True
                                        )
                                        context['pygwalker_html'] = mark_safe(pyg_html)
                                        context['row_count'] = len(df)
                                        context['sample_count'] = len(sampled_df)
                                        context['columns_count'] = len(df.columns)
                                        context['columns_list'] = list(df.columns)

                                    # Clean up temporary file
                                    try:
                                        os.unlink(tmp_file_path)
                                    except Exception as e:
                                        print(f"Error cleaning up temp file: {e}")
            except (ValueError, IndexError) as e:
                context['error'] = f"Invalid file index: {file_index}"

        return render(request, 'dataset/dataset_files.html', context)

    except Dataset.DoesNotExist:
        return render(request, 'dataset/dataset_files.html', {'error': 'Dataset not found'})
    except PermissionDenied:
        raise
    except Exception as e:
        print(f"Unexpected error in dataset_files_fa: {str(e)}")
        return render(request, 'dataset/dataset_files.html', {'error': f'An unexpected error occurred: {str(e)}'})
###################################################
# Download dataset file using Presigned URLs
###################################################

@login_required
def download_file_from_cloud(request):
    """
    Serve file through Django to avoid CORS issues
    """
    dataset_id = request.GET.get('dataset_id')
    try:
        file_index = int(request.GET.get('file_index', 0))
    except (TypeError, ValueError):
        return HttpResponseRedirect('/download-error/')

    if not dataset_id:
        return HttpResponseRedirect('/download-error/')

    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)
        if not can_access_dataset(request.user, dataset):
            raise PermissionDenied
        download_links = dataset.downloadLink

        if not download_links or not isinstance(download_links, list):
            return HttpResponseRedirect('/download-error/')

        if file_index >= len(download_links) or file_index < 0:
            return HttpResponseRedirect('/download-error/')

        # Get file info from database
        file_info = download_links[file_index]
        bucket_name = file_info.get('bucket_name')
        object_key = file_info.get('object_key')

        if not bucket_name or not object_key:
            return HttpResponseRedirect('/download-error/')

        # Generate fresh presigned URL
        expiration = 3600  # 1 hour
        success, presigned_url = generate_presigned_url(bucket_name, object_key, expiration)

        if not success:
            return HttpResponseRedirect('/download-error/')

        response = requests.get(presigned_url, stream=True, timeout=30)
        response.raise_for_status()
        filename = object_key.split('/')[-1]

        def stream_file():
            try:
                yield from response.iter_content(chunk_size=1024 * 1024)
            finally:
                response.close()

        django_response = StreamingHttpResponse(
            stream_file(),
            content_type=response.headers.get('content-type', 'application/octet-stream')
        )
        django_response['Content-Disposition'] = content_disposition_header(
            as_attachment=True,
            filename=filename,
        )
        if response.headers.get('content-length'):
            django_response['Content-Length'] = response.headers['content-length']
        return django_response

    except Dataset.DoesNotExist:
        return HttpResponseRedirect('/download-error/')
    except PermissionDenied:
        raise
    except Exception as e:
        print(f"Download error: {str(e)}")
        return HttpResponseRedirect('/download-error/')


@login_required
def get_file_info(request):
    """
    API endpoint to get file information without downloading
    """
    dataset_id = request.GET.get('dataset_id')

    if not dataset_id:
        return JsonResponse({'error': 'No dataset ID provided'}, status=400)

    try:
        dataset = get_object_or_404(Dataset, id=dataset_id)
        if not can_access_dataset(request.user, dataset):
            raise PermissionDenied
        download_links = dataset.downloadLink

        if not download_links or not isinstance(download_links, list):
            return JsonResponse({'error': 'No download links available'}, status=404)

        file_info = download_links[0]  # Get first file info

        return JsonResponse({
            'filename': file_info['url'].split('/')[-1].split('?')[0],
            'size': file_info['size'],
            'size_human': file_info['size_human'],
            'url': file_info['url']
        })

    except Dataset.DoesNotExist:
        return JsonResponse({'error': 'Dataset not found'}, status=404)
    except PermissionDenied:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    except Exception as e:
        return JsonResponse({'error': 'Unable to retrieve file information'}, status=500)


def check_presigned_url_validity(presigned_url):
    """
    Utility function to check if a presigned URL is still valid
    """
    try:
        response = requests.head(presigned_url, timeout=10)
        return response.status_code == 200
    except:
        return False
###################################################
# Annotation Module
###################################################

@login_required
def dataset_annotation_request_fa(request, pk=None):
    dataset = get_object_or_404(Dataset, id=pk)
    if dataset.user_id != request.user.pk and not request.user.is_superuser:
        raise PermissionDenied

    if request.method == 'POST':
        if 'btn_annotation_request_cancel' in request.POST:
            AnnotationRequest.objects.filter(
                id=request.POST.get('annotation_request_id'),
                dataset=dataset,
            ).update(annotationStatus='Canceled', responseDateTime=datetime.now())

        if 'btn_annotation_response_accept' in request.POST:
            accepted_response = get_object_or_404(
                AnnotationResponse.objects.select_related('annotationRequest').filter(dataset=dataset),
                id=request.POST.get('annotation_response_id'),
                responseType='Request',
            )
            annotation_request = accepted_response.annotationRequest
            total_final_price = annotation_request.totalRecords * accepted_response.suggestedPrice

            AnnotationResponse.objects.filter(
                annotationRequest=annotation_request
            ).exclude(id=accepted_response.id).update(
                responseType='Reject',
                responseDate=datetime.now(),
            )
            accepted_response.responseType = 'Accept'
            accepted_response.responseDate = datetime.now()
            accepted_response.save(update_fields=['responseType', 'responseDate'])
            AnnotationRequest.objects.filter(id=annotation_request.id, dataset=dataset).update(
                annotationStatus='Accepted',
                finalPrice=accepted_response.suggestedPrice,
                totalFinalPrice=total_final_price,
                responseDateTime=datetime.now(),
            )

    annotation_requests = AnnotationRequest.objects.filter(dataset=dataset).order_by('-requestDateTime')
    annotation_responses = AnnotationResponse.objects.filter(dataset=dataset).order_by('-responseDate')
    return render(request, 'dataset/dataset_annotation_request.html',
                  context={'dataset': dataset, 'annotation_requests': annotation_requests,
                           'annotation_responses': annotation_responses})


@login_required
@require_POST
def create_annotation_request(request):
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    try:
        payload = json.loads(request.body)
        annotation = payload['annotationReq']
        start_record = int(annotation['annotationReq_startRecord'])
        end_record = int(annotation['annotationReq_endRecord'])
        if start_record < 1 or end_record < start_record:
            return JsonResponse({'error': 'Invalid record range'}, status=400)

        dataset = get_object_or_404(
            Dataset,
            id=annotation['annotationReq_dataset_id'],
            user=request.user,
        )
        annotation_request = AnnotationRequest.objects.create(
            dataset=dataset,
            user=request.user,
            startRecord=start_record,
            endRecord=end_record,
            totalRecords=end_record - start_record + 1,
            priceType=annotation.get('annotationReq_priceType', 'Pricing'),
            estimatedPrice=annotation.get('annotationReq_estimatedPrice') or 0,
            tags=dataset.dataset_tags,
            desc=annotation.get('annotationReq_desc', ''),
            labelOptions=annotation.get('annotationReq_labelOptions', []),
        )
        return JsonResponse({'status': 'success', 'id': annotation_request.id}, status=201)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid annotation request'}, status=400)


def dataset_annotation_list_fa(request):
    all_annotation_requests = AnnotationRequest.objects.filter(annotationStatus='Requested').select_related(
        'dataset').order_by('-id')
    if request.method == "GET":
        q = request.GET.get('q')
        print(q)
        if q:
            all_annotation_requests = AnnotationRequest.objects.filter(annotationStatus='Requested',
                                                                       tags__icontains=q).select_related(
                'dataset').order_by('-requestDateTime')
    elif request.method == "POST" and 'btn_annotation_request_accept' in request.POST:
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        dataset_id = request.POST.get('dataset_id')
        annotation_request_id = request.POST.get('annotation_request_id')
        annotation_response_price = request.POST.get('annotationRes_suggestedPrice')
        annotation_response_text = request.POST.get('annotationRes_text')

        annotationRequest = get_object_or_404(
            AnnotationRequest,
            id=annotation_request_id,
            dataset_id=dataset_id,
            annotationStatus='Requested',
        )
        dataset = annotationRequest.dataset

        AnnotationResponse.objects.create(dataset=dataset
                                          , annotationRequest=annotationRequest
                                          , user=request.user
                                          , suggestedPrice=annotation_response_price
                                          , text=annotation_response_text
                                          , responseDate=datetime.now()
                                          )

        all_annotation_requests = AnnotationRequest.objects.filter(annotationStatus='Requested').order_by(
            '-requestDateTime').select_related('dataset')
    page_number = request.GET.get('page')
    paginator = Paginator(all_annotation_requests, 9)
    annotation_requests = paginator.get_page(page_number)
    return render(request, 'dataset/dataset_annotation_list.html',
                  context={'annotation_requests': annotation_requests})


def dataset_annotation_record_fa(request, pk=None):
    return render(request, 'dataset/dataset_annotation_record.html', context={})


###################################################
# Debug and Test Functions
###################################################

@login_required
@require_POST
def test_s3_connection(request):
    """Test S3 connection and upload functionality"""
    try:
        s3_client = get_s3_client()

        # Test basic connectivity
        buckets = s3_client.list_buckets()
        bucket_list = [b['Name'] for b in buckets.get('Buckets', [])]

        # Test bucket creation
        test_bucket = "test-bucket-" + str(int(datetime.now().timestamp()))
        s3_client.create_bucket(Bucket=test_bucket)

        # Test file upload
        test_content = b"Hello, World! This is a test file."
        s3_client.put_object(
            Bucket=test_bucket,
            Key="test-file.txt",
            Body=test_content,
            ContentType='text/plain'
        )

        # Test file download
        response = s3_client.get_object(Bucket=test_bucket, Key="test-file.txt")
        downloaded_content = response['Body'].read()

        # Cleanup
        s3_client.delete_object(Bucket=test_bucket, Key="test-file.txt")
        s3_client.delete_bucket(Bucket=test_bucket)

        return JsonResponse({
            'status': 'success',
            'buckets': bucket_list,
            'upload_download_test': 'PASSED',
            'message': 'S3 connection test completed successfully'
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'S3 connection test failed: {str(e)}'
        }, status=500)


###################################################
# Temp functions
###################################################
def dataset_ner(request):
    return render(request, 'dataset/dataset_ner.html', context={})


def analyze_sentiment(comment):
    """Dummy sentiment analysis function - replace with actual implementation"""
    # This is a placeholder - implement your actual sentiment analysis here
    return "POSITIVE", 0.95

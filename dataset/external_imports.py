"""Application service that accepts completed imports from trusted connectors."""

import hashlib
import json
import os
import re

import boto3
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .models import (
    Dataset,
    DatasetAsset,
    DatasetVersion,
    ExternalImportReceipt,
    PipelineDefinition,
)
from .pipeline import enqueue_pipeline


SHA256_RE = re.compile(r'^[a-f0-9]{64}$')
SAFE_PROVIDER_ID_RE = re.compile(r'^[A-Za-z0-9._/-]{1,500}$')


class ImportIdempotencyConflict(Exception):
    """Raised when a request key is reused for a different payload."""


def _required_string(payload, field, max_length):
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError({field: 'This field is required.'})
    value = value.strip()
    if len(value) > max_length:
        raise ValidationError({field: 'This value is too long.'})
    return value


def _validate_import_payload(payload):
    if not isinstance(payload, dict):
        raise ValidationError('The request body must be a JSON object.')

    request_key = _required_string(payload, 'request_key', 255)
    provider = _required_string(payload, 'provider', 20).lower()
    valid_providers = {choice for choice, _label in ExternalImportReceipt.Provider.choices}
    if provider not in valid_providers:
        raise ValidationError({'provider': 'Unsupported provider.'})

    external_id = _required_string(payload, 'external_dataset_id', 500)
    if not SAFE_PROVIDER_ID_RE.fullmatch(external_id) or '..' in external_id:
        raise ValidationError({'external_dataset_id': 'Invalid provider dataset ID.'})

    metadata = payload.get('metadata')
    assets = payload.get('assets')
    if assets is None:
        assets = [payload.get('asset')]
    if not isinstance(metadata, dict) or not isinstance(assets, list):
        raise ValidationError('metadata and assets must be JSON objects and an array.')
    if not 1 <= len(assets) <= 50 or any(not isinstance(asset, dict) for asset in assets):
        raise ValidationError('assets must contain between one and fifty objects.')
    name = _required_string(metadata, 'name', 1000)

    try:
        owner_user_id = int(payload.get('owner_user_id'))
    except (TypeError, ValueError):
        raise ValidationError('owner_user_id must be an integer.')
    if owner_user_id < 1:
        raise ValidationError('owner_user_id must be positive.')

    allowed_buckets = set(settings.EXTERNAL_IMPORT_BUCKETS)
    key_prefix = f'external-imports/{provider}/{hashlib.sha256(request_key.encode()).hexdigest()}/'
    normalized_assets = []
    for index, asset in enumerate(assets):
        try:
            byte_size = int(asset.get('byte_size'))
        except (TypeError, ValueError) as exc:
            raise ValidationError({f'assets[{index}].byte_size': 'An integer is required.'}) from exc
        if byte_size < 1:
            raise ValidationError({f'assets[{index}].byte_size': 'A positive value is required.'})
        bucket = _required_string(asset, 'bucket', 255)
        object_key = _required_string(asset, 'object_key', 1024)
        original_name = os.path.basename(_required_string(asset, 'original_name', 255))
        digest = _required_string(asset, 'sha256', 64).lower()
        if not SHA256_RE.fullmatch(digest):
            raise ValidationError({f'assets[{index}].sha256': 'A lowercase SHA-256 digest is required.'})
        if not allowed_buckets or bucket not in allowed_buckets:
            raise ValidationError({f'assets[{index}].bucket': 'Bucket is not approved for imports.'})
        if (
            object_key.startswith('/')
            or '..' in object_key.split('/')
            or not object_key.startswith(key_prefix)
        ):
            raise ValidationError({f'assets[{index}].object_key': 'Object key is outside the import quarantine prefix.'})
        normalized_assets.append({
            'bucket': bucket,
            'object_key': object_key,
            'original_name': original_name,
            'byte_size': byte_size,
            'sha256': digest,
            'media_type': str(asset.get('media_type') or 'application/octet-stream')[:255],
        })

    return {
        'request_key': request_key,
        'provider': provider,
        'external_dataset_id': external_id,
        'owner_user_id': owner_user_id,
        'metadata': metadata,
        'assets': normalized_assets,
        'name': name,
    }


def _verify_object_size(asset):
    storage = settings.CLOUD_STORAGE_CONFIG
    client = boto3.client(
        's3',
        endpoint_url=storage.get('S3_ENDPOINT'),
        aws_access_key_id=storage.get('ACCESS_KEY'),
        aws_secret_access_key=storage.get('SECRET_KEY'),
        region_name=storage.get('REGION', 'us-east-1'),
        verify=True,
    )
    try:
        result = client.head_object(Bucket=asset['bucket'], Key=asset['object_key'])
    except Exception as exc:
        raise ValidationError({'asset.object_key': 'The imported object is not accessible.'}) from exc
    if result.get('ContentLength') != asset['byte_size']:
        raise ValidationError({'asset.byte_size': 'The object size does not match the manifest.'})


def _existing_receipt(request_key, payload_sha256):
    receipt = ExternalImportReceipt.objects.filter(request_key=request_key).select_related(
        'dataset', 'dataset_version',
    ).first()
    if receipt is None:
        return None
    if receipt.payload_sha256 != payload_sha256:
        raise ImportIdempotencyConflict
    return receipt


def accept_external_import(payload):
    """Create a quarantined dataset/version and enqueue the standard pipeline."""
    data = _validate_import_payload(payload)
    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
    ).encode('utf-8')
    payload_sha256 = hashlib.sha256(canonical_payload).hexdigest()
    existing = _existing_receipt(data['request_key'], payload_sha256)
    if existing:
        return existing, False

    for asset in data['assets']:
        _verify_object_size(asset)
    User = get_user_model()
    actor = User.objects.filter(pk=data['owner_user_id'], is_active=True).first()
    if actor is None:
        raise ValidationError({'owner_user_id': 'Active GUI user was not found.'})

    metadata = data['metadata']
    asset_data = data['assets']
    try:
        with transaction.atomic():
            dataset = Dataset.objects.create(
                user=actor,
                name=data['name'],
                owner=str(metadata.get('owner') or '')[:1000],
                internalId=data['external_dataset_id'][:300],
                internalCode=data['external_dataset_id'][:300],
                size=str(sum(asset['byte_size'] for asset in asset_data)),
                format=str(metadata.get('format') or '')[:30],
                language=str(metadata.get('language') or '')[:30],
                desc=str(metadata.get('description') or ''),
                license=str(metadata.get('license') or '')[:100],
                tasks=str(metadata.get('tasks') or '')[:1000],
                columnDataType=metadata.get('schema') if isinstance(metadata.get('schema'), (dict, list)) else None,
                requestRequired='No',
                status='quarantined',
                downloadLink=[
                    {
                        'bucket_name': asset['bucket'],
                        'object_key': asset['object_key'],
                        'size': asset['byte_size'],
                    }
                    for asset in asset_data
                ],
                price=0,
                referenceOwner=data['provider'],
                createType='Transfer',
                dataType=metadata.get('data_type') if metadata.get('data_type') in dict(Dataset.DATA_TYPE) else 'Text',
                dataset_tags=', '.join(str(tag) for tag in metadata.get('tags', []) if isinstance(tag, str))[:2000]
                if isinstance(metadata.get('tags', []), list) else '',
                filesCount=len(asset_data),
                refLink=str(metadata.get('reference_url') or '')[:4000],
            )
            tags = metadata.get('tags', [])
            if isinstance(tags, list):
                clean_tags = [tag.strip()[:100] for tag in tags if isinstance(tag, str) and tag.strip()]
                if clean_tags:
                    dataset.tags.set(clean_tags[:50])

            version = DatasetVersion.objects.create(
                dataset=dataset,
                version=1,
                status=DatasetVersion.Status.DRAFT,
                pipeline_definition_version='standard-tabular:1.0.0',
                checksum_manifest={
                    'source_assets': [
                        {
                            'object_key': asset['object_key'],
                            'sha256': asset['sha256'],
                            'byte_size': asset['byte_size'],
                        }
                        for asset in asset_data
                    ],
                    'provider': data['provider'],
                    'external_dataset_id': data['external_dataset_id'],
                },
                created_by=actor,
            )
            for asset in asset_data:
                DatasetAsset.objects.create(
                    dataset_version=version,
                    kind=DatasetAsset.Kind.SOURCE,
                    object_key=asset['object_key'],
                    storage_bucket=asset['bucket'],
                    original_name=asset['original_name'],
                    media_type=asset['media_type'],
                    byte_size=asset['byte_size'],
                    sha256=asset['sha256'],
                    status='quarantined',
                )
            definition, _ = PipelineDefinition.objects.update_or_create(
                name='standard-tabular',
                version='1.0.0',
                defaults={
                    'definition': {'steps': ['checksum', 'quality']},
                    'is_active': True,
                },
            )
            enqueue_pipeline(
                version.pk,
                definition.pk,
                requested_by=actor,
            )
            receipt = ExternalImportReceipt.objects.create(
                request_key=data['request_key'],
                payload_sha256=payload_sha256,
                provider=data['provider'],
                external_dataset_id=data['external_dataset_id'],
                dataset=dataset,
                dataset_version=version,
                requested_by=actor,
            )
            return receipt, True
    except IntegrityError:
        # Concurrent retries can race before the unique idempotency receipt exists.
        receipt = _existing_receipt(data['request_key'], payload_sha256)
        if receipt is None:
            raise
        return receipt, False

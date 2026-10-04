"""Signed internal endpoint for completed provider imports."""

import hashlib
import hmac
import json
import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .external_imports import ImportIdempotencyConflict, accept_external_import


@csrf_exempt
@require_POST
def receive_external_import(request):
    secret = settings.EXTERNAL_IMPORT_HMAC_SECRET
    if not secret:
        return JsonResponse({'error': 'integration_not_configured'}, status=503)
    if len(request.body) > settings.EXTERNAL_IMPORT_MAX_BODY_BYTES:
        return JsonResponse({'error': 'request_too_large'}, status=413)
    if not request.content_type or request.content_type.lower() != 'application/json':
        return JsonResponse({'error': 'application_json_required'}, status=415)

    timestamp = request.headers.get('X-DataHub-Timestamp', '')
    supplied_signature = request.headers.get('X-DataHub-Signature', '')
    try:
        request_time = int(timestamp)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'invalid_signature'}, status=401)
    if abs(int(time.time()) - request_time) > 300:
        return JsonResponse({'error': 'expired_signature'}, status=401)

    expected_signature = hmac.new(
        secret.encode('utf-8'),
        timestamp.encode('ascii') + b'.' + request.body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return JsonResponse({'error': 'invalid_signature'}, status=401)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'error': 'invalid_json'}, status=400)

    try:
        receipt, created = accept_external_import(payload)
    except ImportIdempotencyConflict:
        return JsonResponse({'error': 'idempotency_key_reused'}, status=409)
    except ValidationError as exc:
        return JsonResponse(
            {'error': 'invalid_import', 'details': exc.messages},
            status=400,
        )

    pipeline_run = receipt.dataset_version.pipeline_runs.order_by('-created_at').first()
    return JsonResponse({
        'request_key': receipt.request_key,
        'dataset_id': receipt.dataset_id,
        'dataset_version_id': receipt.dataset_version_id,
        'dataset_status': receipt.dataset.status,
        'pipeline_run_id': pipeline_run.pk if pipeline_run else None,
        'pipeline_status': pipeline_run.status if pipeline_run else None,
        'created': created,
    }, status=202 if created else 200)

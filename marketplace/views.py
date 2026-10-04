from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .services import process_signed_payment_webhook


@csrf_exempt
@require_POST
def payment_webhook(request, provider):
    try:
        order, entitlement, created = process_signed_payment_webhook(
            provider,
            request.body,
            request.headers.get('X-Payment-Signature', ''),
        )
    except PermissionDenied:
        raise
    except ValidationError as exc:
        return JsonResponse({
            'status': 'error',
            'message': exc.messages[0] if exc.messages else 'Invalid webhook.',
        }, status=400)
    return JsonResponse({
        'status': 'accepted',
        'order_id': order.id,
        'order_status': order.status,
        'entitlement_id': entitlement.id if entitlement else None,
        'event_created': created,
    })

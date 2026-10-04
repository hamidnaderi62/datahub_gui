from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from dataset.models import DatasetVersion

from .models import Entitlement, Listing, Order, PaymentEvent


def _is_seller(actor, version):
    return actor.is_superuser or version.dataset.user_id == actor.pk


def create_listing(version_id, seller, amount_minor, currency='USD', access_model=Listing.AccessModel.PAID):
    if not getattr(seller, 'is_authenticated', False):
        raise PermissionDenied('Authentication is required to create a listing.')
    version = DatasetVersion.objects.select_related('dataset').get(pk=version_id)
    if not _is_seller(seller, version):
        raise PermissionDenied('Only the dataset owner can create a listing.')
    if version.status != DatasetVersion.Status.PUBLISHED:
        raise ValidationError('Only published versions can be listed.')
    if amount_minor < 0:
        raise ValidationError('Listing amount cannot be negative.')
    if access_model == Listing.AccessModel.PAID and amount_minor == 0:
        raise ValidationError('Paid listings require a positive amount.')
    if access_model == Listing.AccessModel.FREE:
        amount_minor = 0
    return Listing.objects.create(
        dataset_version=version,
        seller=seller,
        amount_minor=amount_minor,
        currency=currency.upper(),
        access_model=access_model,
    )


def create_order(listing_id, buyer, idempotency_key):
    if not getattr(buyer, 'is_authenticated', False):
        raise PermissionDenied('Authentication is required to create an order.')
    if not idempotency_key or len(idempotency_key) > 160:
        raise ValidationError('A valid idempotency key is required.')
    with transaction.atomic():
        listing = Listing.objects.select_for_update().select_related(
            'dataset_version__dataset',
        ).get(pk=listing_id)
        if listing.status != Listing.Status.ACTIVE:
            raise ValidationError('Listing is not active.')
        if listing.dataset_version.status != DatasetVersion.Status.PUBLISHED:
            raise ValidationError('Only published versions can be purchased.')
        if listing.seller_id == buyer.pk:
            raise ValidationError('A seller cannot purchase its own listing.')
        if listing.access_model == Listing.AccessModel.REQUEST:
            raise ValidationError('This listing requires approval before checkout.')
        order, _ = Order.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                'listing': listing,
                'buyer': buyer,
                'amount_minor': listing.amount_minor,
                'currency': listing.currency,
            },
        )
        if order.listing_id != listing.id or order.buyer_id != buyer.pk:
            raise ValidationError('Idempotency key is already used by another order.')
        return order


def record_payment_event(provider, provider_event_id, order_id, status, amount_minor, currency, payload=None):
    """Record an idempotent provider event and grant access only on success."""
    if not provider_event_id:
        raise ValidationError('Payment provider event ID is required.')
    with transaction.atomic():
        order = Order.objects.select_for_update().select_related(
            'listing__dataset_version',
        ).get(pk=order_id)
        existing = PaymentEvent.objects.filter(
            provider=provider,
            provider_event_id=provider_event_id,
        ).first()
        if existing:
            if existing.order_id != order.id:
                raise ValidationError('Payment event is bound to another order.')
            return order, Entitlement.objects.filter(order=order).first(), False
        if amount_minor != order.amount_minor or currency.upper() != order.currency:
            raise ValidationError('Payment amount or currency does not match the order.')
        event = PaymentEvent.objects.create(
            provider=provider,
            provider_event_id=provider_event_id,
            order=order,
            status=status,
            amount_minor=amount_minor,
            currency=currency.upper(),
            payload=payload or {},
        )
        if status != 'succeeded':
            order.status = Order.Status.FAILED
            order.save(update_fields=['status'])
            return order, None, True
        order.status = Order.Status.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=['status', 'paid_at'])
        entitlement, _ = Entitlement.objects.get_or_create(
            buyer=order.buyer,
            dataset_version=order.listing.dataset_version,
            defaults={
                'order': order,
                'status': Entitlement.Status.ACTIVE,
                'starts_at': timezone.now(),
            },
        )
        if entitlement.order_id != order.id:
            raise ValidationError('Buyer already has an entitlement for this version.')
        LedgerEntry.objects.get_or_create(
            entry_key=f'order:{order.id}:credit',
            defaults={
                'order': order,
                'seller': order.listing.seller,
                'direction': LedgerEntry.Direction.CREDIT,
                'amount_minor': order.amount_minor,
                'currency': order.currency,
            },
        )
        return order, entitlement, True


def has_active_entitlement(user, dataset):
    if not getattr(user, 'is_authenticated', False):
        return False
    now = timezone.now()
    return Entitlement.objects.filter(
        buyer=user,
        dataset_version__dataset=dataset,
        status=Entitlement.Status.ACTIVE,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).exists()


import hashlib
import hmac
import json

from django.conf import settings

from .models import LedgerEntry, Refund


def verify_webhook_signature(raw_body, signature):
    secret = getattr(settings, 'PAYMENT_WEBHOOK_SECRET', '')
    if not secret or not signature:
        return False
    supplied = signature.removeprefix('sha256=')
    expected = hmac.new(
        secret.encode('utf-8'),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, supplied)


def process_signed_payment_webhook(provider, raw_body, signature):
    if not verify_webhook_signature(raw_body, signature):
        raise PermissionDenied('Invalid payment webhook signature.')
    try:
        payload = json.loads(raw_body.decode('utf-8'))
        event_id = payload['event_id']
        order_id = int(payload['order_id'])
        status = payload['status']
        amount_minor = int(payload['amount_minor'])
        currency = str(payload['currency']).upper()
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError('Invalid payment webhook payload.') from exc

    order, entitlement, created = record_payment_event(
        provider=provider,
        provider_event_id=event_id,
        order_id=order_id,
        status=status,
        amount_minor=amount_minor,
        currency=currency,
        payload=payload,
    )
    return order, entitlement, created


def record_refund(provider_ref, order_id, amount_minor, currency, status='succeeded'):
    with transaction.atomic():
        order = Order.objects.select_for_update().select_related(
            'listing__dataset_version',
        ).get(pk=order_id)
        existing = Refund.objects.filter(provider_ref=provider_ref).first()
        if existing:
            return existing
        if status == Refund.Status.SUCCEEDED:
            if order.status != Order.Status.PAID:
                raise ValidationError('Only paid orders can be refunded.')
            if amount_minor <= 0 or amount_minor > order.amount_minor:
                raise ValidationError('Refund amount is outside the order amount.')
            if currency.upper() != order.currency:
                raise ValidationError('Refund currency does not match the order.')
        refund = Refund.objects.create(
            order=order,
            provider_ref=provider_ref,
            amount_minor=amount_minor,
            currency=currency.upper(),
            status=status,
        )
        if status == Refund.Status.SUCCEEDED:
            order.status = Order.Status.REFUNDED
            order.save(update_fields=['status'])
            Entitlement.objects.filter(
                order=order,
                status=Entitlement.Status.ACTIVE,
            ).update(status=Entitlement.Status.REVOKED)
            LedgerEntry.objects.get_or_create(
                entry_key=f'refund:{refund.id}:debit',
                defaults={
                    'order': order,
                    'seller': order.listing.seller,
                    'direction': LedgerEntry.Direction.DEBIT,
                    'amount_minor': amount_minor,
                    'currency': currency.upper(),
                },
            )
        return refund

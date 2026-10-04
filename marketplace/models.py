from django.contrib.auth.models import User
from django.db import models

from dataset.models import DatasetVersion


class Listing(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        PAUSED = 'paused', 'Paused'
        ARCHIVED = 'archived', 'Archived'

    class AccessModel(models.TextChoices):
        FREE = 'free', 'Free'
        PAID = 'paid', 'Paid'
        REQUEST = 'request', 'Request approval'

    dataset_version = models.OneToOneField(
        DatasetVersion,
        on_delete=models.PROTECT,
        related_name='listing',
    )
    seller = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='dataset_listings',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    access_model = models.CharField(
        max_length=20,
        choices=AccessModel.choices,
        default=AccessModel.PAID,
    )
    currency = models.CharField(max_length=3, default='USD')
    amount_minor = models.PositiveBigIntegerField(default=0)
    terms_version = models.CharField(max_length=80, default='1')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.dataset_version_id}:{self.currency}{self.amount_minor}'


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    listing = models.ForeignKey(
        Listing,
        on_delete=models.PROTECT,
        related_name='orders',
    )
    buyer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='dataset_orders',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    idempotency_key = models.CharField(max_length=160, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.idempotency_key


class Entitlement(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        REVOKED = 'revoked', 'Revoked'
        EXPIRED = 'expired', 'Expired'

    buyer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='dataset_entitlements',
    )
    dataset_version = models.ForeignKey(
        DatasetVersion,
        on_delete=models.PROTECT,
        related_name='entitlements',
    )
    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name='entitlement',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('buyer', 'dataset_version'),
                name='unique_buyer_dataset_entitlement',
            ),
        ]


class PaymentEvent(models.Model):
    provider = models.CharField(max_length=40)
    provider_event_id = models.CharField(max_length=180)
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name='payment_events',
    )
    status = models.CharField(max_length=30)
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('provider', 'provider_event_id'),
                name='unique_payment_provider_event',
            ),
        ]


class LedgerEntry(models.Model):
    class Direction(models.TextChoices):
        CREDIT = 'credit', 'Credit'
        DEBIT = 'debit', 'Debit'

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name='ledger_entries',
    )
    seller = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='marketplace_ledger_entries',
    )
    entry_key = models.CharField(max_length=180, unique=True)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    created_at = models.DateTimeField(auto_now_add=True)


class Refund(models.Model):
    class Status(models.TextChoices):
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Failed'

    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name='refunds',
    )
    provider_ref = models.CharField(max_length=180, unique=True)
    amount_minor = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20, choices=Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)

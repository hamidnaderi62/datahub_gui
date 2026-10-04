import hashlib
import hmac
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings

from dataset.models import Dataset, DatasetVersion
from dataset.views import can_access_dataset

from .models import Entitlement, LedgerEntry, Listing, Order, PaymentEvent
from .services import (
    create_listing,
    create_order,
    process_signed_payment_webhook,
    record_payment_event,
    record_refund,
)


User = get_user_model()


class MarketplaceEntitlementTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user('market-seller')
        self.buyer = User.objects.create_user('market-buyer')
        self.dataset = Dataset.objects.create(
            user=self.seller,
            name='Paid marketplace dataset',
            price='25.00',
            requestRequired='No',
            status='published',
        )
        self.version = DatasetVersion.objects.create(
            dataset=self.dataset,
            version=1,
            status=DatasetVersion.Status.PUBLISHED,
            created_by=self.seller,
            published_by=self.seller,
        )
        self.listing = create_listing(
            self.version.id,
            self.seller,
            amount_minor=2500,
            currency='USD',
        )

    def test_paid_dataset_requires_and_receives_entitlement(self):
        self.assertFalse(can_access_dataset(self.buyer, self.dataset))
        order = create_order(self.listing.id, self.buyer, 'order-1')
        self.assertEqual(order.status, Order.Status.PENDING)

        paid, entitlement, created = record_payment_event(
            provider='test-provider',
            provider_event_id='evt-1',
            order_id=order.id,
            status='succeeded',
            amount_minor=2500,
            currency='USD',
        )

        self.assertTrue(created)
        self.assertEqual(paid.status, Order.Status.PAID)
        self.assertEqual(entitlement.status, Entitlement.Status.ACTIVE)
        self.assertTrue(can_access_dataset(self.buyer, self.dataset))

    def test_order_and_payment_event_are_idempotent(self):
        first = create_order(self.listing.id, self.buyer, 'same-key')
        second = create_order(self.listing.id, self.buyer, 'same-key')
        self.assertEqual(first.id, second.id)

        record_payment_event(
            'test-provider', 'evt-same', first.id, 'succeeded', 2500, 'USD'
        )
        _, entitlement, created = record_payment_event(
            'test-provider', 'evt-same', first.id, 'succeeded', 2500, 'USD'
        )

        self.assertFalse(created)
        self.assertEqual(Entitlement.objects.filter(buyer=self.buyer).count(), 1)
        self.assertEqual(entitlement.order_id, first.id)
        self.assertEqual(PaymentEvent.objects.count(), 1)

    def test_payment_amount_mismatch_does_not_grant_access(self):
        order = create_order(self.listing.id, self.buyer, 'order-mismatch')
        with self.assertRaises(ValidationError):
            record_payment_event(
                'test-provider', 'evt-mismatch', order.id, 'succeeded', 1, 'USD'
            )
        self.assertFalse(can_access_dataset(self.buyer, self.dataset))

    def test_listing_requires_published_version(self):
        draft_dataset = Dataset.objects.create(
            user=self.seller,
            name='Draft dataset',
            status='draft',
        )
        draft = DatasetVersion.objects.create(
            dataset=draft_dataset,
            version=1,
            status=DatasetVersion.Status.DRAFT,
            created_by=self.seller,
        )
        with self.assertRaises(ValidationError):
            create_listing(draft.id, self.seller, 100, 'USD')


class PaymentWebhookTests(MarketplaceEntitlementTests):
    @override_settings(PAYMENT_WEBHOOK_SECRET='webhook-secret')
    def test_signed_webhook_is_idempotent_and_creates_ledger(self):
        order = create_order(self.listing.id, self.buyer, 'webhook-order')
        payload = {
            'event_id': 'evt-webhook',
            'order_id': order.id,
            'status': 'succeeded',
            'amount_minor': 2500,
            'currency': 'USD',
        }
        raw = json.dumps(payload).encode('utf-8')
        signature = hmac.new(
            b'webhook-secret', raw, hashlib.sha256
        ).hexdigest()
        client = Client(HTTP_HOST='localhost')

        first = client.post(
            '/marketplace/webhooks/test-provider',
            raw,
            content_type='application/json',
            HTTP_X_PAYMENT_SIGNATURE=f'sha256={signature}',
        )
        second = client.post(
            '/marketplace/webhooks/test-provider',
            raw,
            content_type='application/json',
            HTTP_X_PAYMENT_SIGNATURE=f'sha256={signature}',
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.json()['event_created'])
        self.assertFalse(second.json()['event_created'])
        self.assertEqual(LedgerEntry.objects.count(), 1)
        self.assertEqual(Entitlement.objects.count(), 1)

    @override_settings(PAYMENT_WEBHOOK_SECRET='webhook-secret')
    def test_invalid_webhook_signature_is_rejected(self):
        with self.assertRaises(PermissionDenied):
            process_signed_payment_webhook(
                'test-provider', b'{}', 'sha256=invalid'
            )

    def test_refund_revokes_entitlement_and_posts_debit(self):
        order = create_order(self.listing.id, self.buyer, 'refund-order')
        record_payment_event(
            'test-provider', 'evt-refund', order.id, 'succeeded', 2500, 'USD'
        )

        refund = record_refund('refund-1', order.id, 2500, 'USD')

        self.assertEqual(refund.status, 'succeeded')
        self.assertEqual(
            Order.objects.get(pk=order.id).status,
            Order.Status.REFUNDED,
        )
        self.assertEqual(
            Entitlement.objects.get(order=order).status,
            Entitlement.Status.REVOKED,
        )
        self.assertEqual(LedgerEntry.objects.count(), 2)

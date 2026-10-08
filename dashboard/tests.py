from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from dataset.models import Dataset

from .models import ProviderImportRequest
from .views import _normalize_provider_id

User = get_user_model()


@override_settings(EXTERNAL_IMPORT_HMAC_SECRET='test-secret', DATAHUB_API_IMPORT_URL='http://api.test/import-jobs/')
class DashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('ops', 'ops@example.com', 'pass12345', is_staff=True)
        self.owner = User.objects.create_user('owner', 'owner@example.com', 'pass12345')
        self.client.force_login(self.admin)

    def test_staff_can_open_overview_and_dataset_queue(self):
        Dataset.objects.create(user=self.owner, name='Reviewed corpus', status='needs_review')
        response = self.client.get(reverse('dashboard:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reviewed corpus')
        self.assertEqual(self.client.get(reverse('dashboard:datasets')).status_code, 200)
        self.assertEqual(self.client.get(reverse('dashboard:users')).status_code, 200)
        self.assertEqual(self.client.get(reverse('dashboard:orders')).status_code, 200)
        self.assertEqual(self.client.get(reverse('dashboard:imports')).status_code, 200)

    def test_non_staff_is_redirected(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse('dashboard:overview'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/account/', response['Location'])

    def test_provider_url_is_normalized_to_dataset_id(self):
        self.assertEqual(
            _normalize_provider_id('huggingface', 'https://huggingface.co/datasets/lhoestq/demo1'),
            'lhoestq/demo1',
        )
        self.assertEqual(
            _normalize_provider_id('kaggle', 'https://www.kaggle.com/datasets/uciml/iris/'),
            'uciml/iris',
        )

    @patch('dashboard.views.requests.request')
    def test_provider_import_is_signed_and_tracked(self, request_mock):
        response = Mock(status_code=202)
        response.json.return_value = {'id': '4bd3a6c8-4a69-4eab-882f-1c9cb0b2d020', 'status': 'queued'}
        request_mock.return_value = response
        result = self.client.post(reverse('dashboard:imports'), {
            'provider': 'huggingface', 'provider_dataset_id': 'org/corpus', 'owner_id': self.owner.pk,
        })
        self.assertRedirects(result, reverse('dashboard:imports'))
        self.assertEqual(ProviderImportRequest.objects.count(), 1)
        self.assertEqual(request_mock.call_args.kwargs['headers']['Content-Type'], 'application/json')
        self.assertTrue(request_mock.call_args.kwargs['headers']['X-DataHub-Signature'])

    @patch('dashboard.views.requests.request')
    def test_import_status_updates_local_record(self, request_mock):
        record = ProviderImportRequest.objects.create(
            api_job_id='4bd3a6c8-4a69-4eab-882f-1c9cb0b2d020', request_key='key-1', provider='kaggle',
            provider_dataset_id='owner/corpus', owner=self.owner, requested_by=self.admin,
        )
        response = Mock(status_code=200)
        response.json.return_value = {'status': 'succeeded', 'error_code': '', 'gui_dataset_id': 19, 'gui_dataset_version_id': 4}
        request_mock.return_value = response
        result = self.client.get(reverse('dashboard:import_status', args=[record.pk]))
        self.assertEqual(result.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.status, 'succeeded')
        self.assertEqual(record.gui_dataset_id, 19)
        self.assertEqual(request_mock.call_args.kwargs['data'], b'')

    def test_recent_provider_job_keeps_actions_in_responsive_row(self):
        ProviderImportRequest.objects.create(
            api_job_id='4bd3a6c8-4a69-4eab-882f-1c9cb0b2d020',
            request_key='long-provider-id',
            provider='kaggle',
            provider_dataset_id=f"owner/{'long-dataset-name-' * 25}",
            owner=self.owner,
            requested_by=self.admin,
        )

        response = self.client.get(reverse('dashboard:imports'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ops-import-actions')
        self.assertContains(response, 'js-refresh-import')

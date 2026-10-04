import hashlib
import io
import json
import shutil
import tempfile
import zipfile
from datetime import timedelta
from unittest.mock import MagicMock, patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import (
    Dataset,
    DatasetAsset,
    DatasetVersion,
    PipelineDefinition,
    PipelineRun,
    PipelineStepRun,
    QualityReport,
    UploadBatch,
    UploadPart,
    UploadSession,
)
from .pipeline import (
    QualityGateError,
    _archive_member_metrics,
    complete_pipeline_run,
    enqueue_pipeline,
    fail_pipeline_run,
    process_pipeline_run,
    publish_dataset_version,
    start_pipeline_run,
)
from .views import can_access_dataset


User = get_user_model()


class DatasetAccessPolicyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('dataset-owner')
        self.buyer = User.objects.create_user('dataset-buyer')
        self.free_dataset = Dataset.objects.create(
            user=self.owner,
            name='Free dataset',
            price=0,
            requestRequired='No',
        )
        self.paid_dataset = Dataset.objects.create(
            user=self.owner,
            name='Paid dataset',
            price='10.00',
            requestRequired='No',
        )
        self.requested_dataset = Dataset.objects.create(
            user=self.owner,
            name='Requested dataset',
            price=0,
            requestRequired='Yes',
        )

    def test_public_free_dataset_is_readable(self):
        self.assertTrue(can_access_dataset(AnonymousUser(), self.free_dataset))

    def test_paid_dataset_is_denied_without_entitlement(self):
        self.assertFalse(can_access_dataset(self.buyer, self.paid_dataset))

    def test_owner_can_access_owned_dataset(self):
        self.assertTrue(can_access_dataset(self.owner, self.paid_dataset))

    def test_request_required_dataset_needs_acceptance(self):
        self.assertFalse(can_access_dataset(self.buyer, self.requested_dataset))
        self.requested_dataset.requests.create(
            user=self.buyer,
            responseType='Accept',
        )
        self.assertTrue(can_access_dataset(self.buyer, self.requested_dataset))


class PipelineLifecycleTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.mkdtemp(prefix='datahub-pipeline-media-')
        self.media_override = override_settings(MEDIA_ROOT=self.media_dir)
        self.media_override.enable()
        self.owner = User.objects.create_user('pipeline-owner')
        self.dataset = Dataset.objects.create(
            user=self.owner,
            name='Pipeline dataset',
            status='quarantined',
        )
        self.version = DatasetVersion.objects.create(
            dataset=self.dataset,
            version=1,
            created_by=self.owner,
            checksum_manifest={'source_sha256': 'abc'},
        )
        self.definition = PipelineDefinition.objects.create(
            name='standard-tabular',
            version='1.0.0',
            definition={'steps': ['checksum', {'key': 'quality'}]},
        )

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_dir, ignore_errors=True)

    @override_settings(PIPELINE_AUTO_DISPATCH=True)
    @patch('dataset.pipeline._dispatch_pipeline_run')
    def test_queued_run_dispatches_after_commit(self, dispatch):
        with self.captureOnCommitCallbacks(execute=True):
            run, _ = enqueue_pipeline(self.version.id, self.definition.id)

        dispatch.assert_called_once_with(run.id)

    @override_settings(PIPELINE_RUN_STALE_AFTER_SECONDS=60)
    def test_stale_running_run_can_be_reclaimed(self):
        run, _ = enqueue_pipeline(self.version.id, self.definition.id)
        start_pipeline_run(run.id)
        run.started_at = timezone.now() - timedelta(minutes=5)
        run.save(update_fields=['started_at'])

        reclaimed = start_pipeline_run(run.id)

        self.assertEqual(reclaimed.status, PipelineRun.Status.RUNNING)
        self.assertGreater(reclaimed.started_at, timezone.now() - timedelta(minutes=1))

    def test_enqueue_is_idempotent_and_creates_steps(self):
        first, created = enqueue_pipeline(
            self.version.id,
            self.definition.id,
            requested_by=self.owner,
        )
        second, created_again = enqueue_pipeline(
            self.version.id,
            self.definition.id,
            requested_by=self.owner,
        )

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            DatasetVersion.objects.get(pk=self.version.pk).status,
            DatasetVersion.Status.PROCESSING,
        )
        start_pipeline_run(first.id)
        self.assertEqual(
            PipelineStepRun.objects.filter(pipeline_run=first).count(),
            2,
        )

    def test_pipeline_status_is_owner_scoped(self):
        run, _ = enqueue_pipeline(self.version.id, self.definition.id, requested_by=self.owner)
        client = Client(HTTP_HOST='localhost')
        client.force_login(self.owner)
        response = client.get(f'/dataset/pipeline_status/{self.version.id}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['pipeline_run_id'], run.id)
        self.assertEqual(response.json()['pipeline_status'], PipelineRun.Status.QUEUED)
        detail = client.get(f'/dataset/dataset_detail/{self.dataset.id}')
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'ti-shield-check')

    def test_completion_stops_at_review(self):
        run, _ = enqueue_pipeline(self.version.id, self.definition.id)
        start_pipeline_run(run.id)
        complete_pipeline_run(
            run.id,
            QualityReport.Result.REVIEW,
            metrics={'rows': 12},
            score='98.50',
        )

        run.refresh_from_db()
        self.version.refresh_from_db()
        self.dataset.refresh_from_db()
        self.assertEqual(run.status, PipelineRun.Status.SUCCEEDED)
        self.assertEqual(self.version.status, DatasetVersion.Status.NEEDS_REVIEW)
        self.assertEqual(self.dataset.status, 'needs_review')
        self.assertEqual(self.version.quality_report.metrics['rows'], 12)

    def test_worker_metadata_gate_stops_at_review(self):
        source = b'name,age\nAda,36\n'
        source_path = default_storage.save(
            'pipeline/sample.csv',
            ContentFile(source),
        )
        DatasetAsset.objects.create(
            dataset_version=self.version,
            kind=DatasetAsset.Kind.SOURCE,
            object_key=source_path,
            original_name='sample.csv',
            byte_size=len(source),
            sha256=hashlib.sha256(source).hexdigest(),
        )
        run, _ = enqueue_pipeline(self.version.id, self.definition.id)

        processed = process_pipeline_run(run.id)

        self.assertEqual(processed.status, PipelineRun.Status.SUCCEEDED)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DatasetVersion.Status.NEEDS_REVIEW)
        self.assertEqual(processed.steps.filter(status='succeeded').count(), 2)
        self.assertEqual(processed.output_manifest['assets'][0]['rows_sampled'], 1)
        self.assertEqual(processed.output_manifest['assets'][0]['columns'], ['name', 'age'])
        self.assertEqual(self.version.assets.get(kind=DatasetAsset.Kind.PREVIEW).media_type, 'text/csv')
        normalized = self.version.assets.get(kind=DatasetAsset.Kind.DERIVED)
        self.assertEqual(normalized.media_type, 'application/vnd.apache.parquet')
        self.assertEqual(processed.output_manifest['assets'][0]['normalization']['status'], 'created')
        self.assertGreater(normalized.byte_size, 0)

    def test_worker_marks_pii_column_signal_without_auto_redaction(self):
        source = b'email,name\nada@example.com,Ada\n'
        source_path = default_storage.save(
            'pipeline/pii.csv',
            ContentFile(source),
        )
        DatasetAsset.objects.create(
            dataset_version=self.version,
            kind=DatasetAsset.Kind.SOURCE,
            object_key=source_path,
            original_name='pii.csv',
            byte_size=len(source),
            sha256=hashlib.sha256(source).hexdigest(),
        )
        run, _ = enqueue_pipeline(self.version.id, self.definition.id)

        processed = process_pipeline_run(run.id)

        report = processed.output_manifest['assets'][0]
        self.assertTrue(report['pii_detected'])
        self.assertEqual(report['pii_columns'], ['email'])
        self.assertEqual(report['rows_sampled'], 1)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, DatasetVersion.Status.NEEDS_REVIEW)

    def test_pii_values_are_detected_and_redacted_from_preview(self):
        source = b'contact,name\nada@example.com,Ada\n'
        source_path = default_storage.save('pipeline/pii-preview.csv', ContentFile(source))
        DatasetAsset.objects.create(
            dataset_version=self.version,
            kind=DatasetAsset.Kind.SOURCE,
            object_key=source_path,
            original_name='pii-preview.csv',
            byte_size=len(source),
            sha256=hashlib.sha256(source).hexdigest(),
        )
        run, _ = enqueue_pipeline(self.version.id, self.definition.id)

        processed = process_pipeline_run(run.id)

        self.assertEqual(processed.status, PipelineRun.Status.SUCCEEDED)
        metrics = processed.output_manifest['assets'][0]
        self.assertTrue(metrics['value_pii_detected'])
        preview = self.version.assets.get(kind=DatasetAsset.Kind.PREVIEW, original_name__endswith='.csv')
        with default_storage.open(preview.object_key, 'rb') as file_data:
            preview_text = file_data.read().decode('utf-8')
        self.assertNotIn('ada@example.com', preview_text)
        self.assertIn('[REDACTED]', preview_text)

    def test_checksum_mismatch_fails_quality_gate(self):
        source = b'name\nAda\n'
        source_path = default_storage.save(
            'pipeline/bad.csv',
            ContentFile(source),
        )
        DatasetAsset.objects.create(
            dataset_version=self.version,
            kind=DatasetAsset.Kind.SOURCE,
            object_key=source_path,
            original_name='bad.csv',
            byte_size=len(source),
            sha256='a' * 64,
        )
        run, _ = enqueue_pipeline(self.version.id, self.definition.id)

        processed = process_pipeline_run(run.id)

        self.assertEqual(processed.status, PipelineRun.Status.FAILED)
        self.assertEqual(processed.error_code, 'CHECKSUM_MISMATCH')

    def test_zip_archive_reports_image_manifest_without_extracting(self):
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, 'w') as archive:
            archive.writestr('train/cat.jpg', b'jpeg-data')
            archive.writestr('train/dog.png', b'png-data')
            archive.writestr('README.txt', b'images')
        source = archive_buffer.getvalue()
        source_path = default_storage.save('pipeline/images.zip', ContentFile(source))
        DatasetAsset.objects.create(
            dataset_version=self.version,
            kind=DatasetAsset.Kind.SOURCE,
            object_key=source_path,
            original_name='images.zip',
            byte_size=len(source),
            sha256=hashlib.sha256(source).hexdigest(),
        )
        run, _ = enqueue_pipeline(self.version.id, self.definition.id)

        processed = process_pipeline_run(run.id)

        self.assertEqual(processed.status, PipelineRun.Status.SUCCEEDED)
        report = processed.output_manifest['assets'][0]
        self.assertEqual(report['archive_validation'], 'validated')
        self.assertEqual(report['member_count'], 3)
        self.assertEqual(report['image_count'], 2)
        self.assertEqual(report['image_extensions'], ['jpg', 'png'])

    def test_zip_archive_profiles_valid_images_and_duplicates(self):
        first = io.BytesIO()
        image = Image.new('RGB', (3, 2), color='red')
        image.save(first, format='PNG')
        image.close()
        image_bytes = first.getvalue()
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, 'w') as archive:
            archive.writestr('a/one.png', image_bytes)
            archive.writestr('b/two.png', image_bytes)
        source = archive_buffer.getvalue()
        source_path = default_storage.save('pipeline/profiled-images.zip', ContentFile(source))
        DatasetAsset.objects.create(
            dataset_version=self.version,
            kind=DatasetAsset.Kind.SOURCE,
            object_key=source_path,
            original_name='profiled-images.zip',
            byte_size=len(source),
            sha256=hashlib.sha256(source).hexdigest(),
        )
        run, _ = enqueue_pipeline(self.version.id, self.definition.id)

        processed = process_pipeline_run(run.id)

        self.assertEqual(processed.status, PipelineRun.Status.SUCCEEDED)
        profile = processed.output_manifest['assets'][0]['image_profile']
        self.assertEqual(profile['sampled_count'], 2)
        self.assertEqual(profile['corrupt_count'], 0)
        self.assertEqual(profile['duplicate_count'], 1)
        self.assertEqual(profile['dimensions'], {'min_width': 3, 'max_width': 3, 'min_height': 2, 'max_height': 2})
        preview = self.version.assets.get(kind=DatasetAsset.Kind.PREVIEW)
        self.assertEqual(preview.media_type, 'image/jpeg')
        self.assertGreater(preview.byte_size, 0)
        self.assertEqual(processed.output_manifest['derived_assets'][0]['asset_id'], preview.id)
        self.assertEqual(processed.output_manifest['assets'][0]['image_normalization']['count'], 2)
        self.assertEqual(self.version.assets.filter(kind=DatasetAsset.Kind.DERIVED).count(), 2)

    def test_zip_archive_path_traversal_fails_quality_gate(self):
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, 'w') as archive:
            archive.writestr('../escape.jpg', b'unsafe')
        source = archive_buffer.getvalue()
        source_path = default_storage.save('pipeline/unsafe.zip', ContentFile(source))
        DatasetAsset.objects.create(
            dataset_version=self.version,
            kind=DatasetAsset.Kind.SOURCE,
            object_key=source_path,
            original_name='unsafe.zip',
            byte_size=len(source),
            sha256=hashlib.sha256(source).hexdigest(),
        )
        run, _ = enqueue_pipeline(self.version.id, self.definition.id)

        processed = process_pipeline_run(run.id)

        self.assertEqual(processed.status, PipelineRun.Status.FAILED)
        self.assertEqual(processed.error_code, 'ARCHIVE_UNSAFE_PATH')

    def test_binary_signature_mismatch_fails_quality_gate(self):
        source = b'name\nAda\n'
        source_path = default_storage.save('pipeline/not-an-image.jpg', ContentFile(source))
        DatasetAsset.objects.create(
            dataset_version=self.version,
            kind=DatasetAsset.Kind.SOURCE,
            object_key=source_path,
            original_name='not-an-image.jpg',
            byte_size=len(source),
            sha256=hashlib.sha256(source).hexdigest(),
        )
        run, _ = enqueue_pipeline(self.version.id, self.definition.id)

        processed = process_pipeline_run(run.id)

        self.assertEqual(processed.status, PipelineRun.Status.FAILED)
        self.assertEqual(processed.error_code, 'SOURCE_TYPE_MISMATCH')

    def test_encrypted_archive_members_are_rejected(self):
        class EncryptedMember:
            filename = 'secret.jpg'
            flag_bits = 0x1
            external_attr = 0
            file_size = 1
            compress_size = 1

            @staticmethod
            def is_dir():
                return False

        with self.assertRaises(QualityGateError) as error:
            _archive_member_metrics([EncryptedMember()], 'zip')
        self.assertEqual(error.exception.code, 'ARCHIVE_ENCRYPTED')

    def test_failure_is_terminal_and_propagates(self):
        run, _ = enqueue_pipeline(self.version.id, self.definition.id)
        start_pipeline_run(run.id)
        fail_pipeline_run(run.id, 'CHECKSUM_MISMATCH')

        run.refresh_from_db()
        self.version.refresh_from_db()
        self.dataset.refresh_from_db()
        self.assertEqual(run.status, PipelineRun.Status.FAILED)
        self.assertEqual(run.error_code, 'CHECKSUM_MISMATCH')
        self.assertEqual(self.version.status, DatasetVersion.Status.FAILED)
        self.assertEqual(self.dataset.status, 'failed')

        retry, created = enqueue_pipeline(self.version.id, self.definition.id)
        self.assertFalse(created)
        self.assertEqual(retry.status, PipelineRun.Status.QUEUED)
        self.version.refresh_from_db()
        self.dataset.refresh_from_db()
        self.assertEqual(self.version.status, DatasetVersion.Status.PROCESSING)
        self.assertEqual(self.dataset.status, 'processing')


class PublicationGateTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('publication-owner')
        self.other = User.objects.create_user('publication-other')
        self.dataset = Dataset.objects.create(
            user=self.owner,
            name='Publication dataset',
            status='needs_review',
        )
        self.version = DatasetVersion.objects.create(
            dataset=self.dataset,
            version=1,
            status=DatasetVersion.Status.NEEDS_REVIEW,
            created_by=self.owner,
        )
        self.asset = DatasetAsset.objects.create(
            dataset_version=self.version,
            kind=DatasetAsset.Kind.SOURCE,
            object_key='sample.csv',
            byte_size=10,
            sha256='a' * 64,
            status='validated',
        )

    def test_owner_can_publish_reviewed_version(self):
        QualityReport.objects.create(
            dataset_version=self.version,
            result=QualityReport.Result.REVIEW,
            metrics={'rows': 1},
        )

        published = publish_dataset_version(self.version.id, self.owner)

        self.assertEqual(published.status, DatasetVersion.Status.PUBLISHED)
        self.assertEqual(published.published_by_id, self.owner.id)
        self.assertEqual(
            Dataset.objects.get(pk=self.dataset.pk).status,
            'published',
        )
        self.assertEqual(
            DatasetAsset.objects.get(pk=self.asset.pk).status,
            'published',
        )

    def test_non_owner_cannot_publish(self):
        QualityReport.objects.create(
            dataset_version=self.version,
            result=QualityReport.Result.PASS,
        )

        with self.assertRaises(PermissionDenied):
            publish_dataset_version(self.version.id, self.other)

    def test_failed_quality_report_cannot_publish(self):
        QualityReport.objects.create(
            dataset_version=self.version,
            result=QualityReport.Result.FAIL,
        )

        with self.assertRaises(ValidationError):
            publish_dataset_version(self.version.id, self.owner)

    def test_owner_publication_endpoint(self):
        QualityReport.objects.create(
            dataset_version=self.version,
            result=QualityReport.Result.PASS,
        )
        client = Client(HTTP_HOST='localhost')
        client.force_login(self.owner)

        response = client.post(
            f'/dataset/publish_dataset_version/{self.version.id}',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['version_status'], 'published')


class PersistentUploadTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.mkdtemp(prefix='datahub-test-media-')
        self.media_override = override_settings(MEDIA_ROOT=self.media_dir)
        self.media_override.enable()
        self.owner = User.objects.create_user('upload-owner')
        self.other = User.objects.create_user('upload-other')

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def _chunk(self, client, number, upload_id=None):
        payload = {
            'chunkNumber': str(number),
            'totalChunks': '2',
            'fileName': 'sample.csv',
            'fileSize': '2',
            'metadata': json.dumps({'dataset_name': 'Upload test'}),
            'file': SimpleUploadedFile('sample.csv', b'a' if number == 0 else b'b'),
        }
        if upload_id:
            payload['uploadId'] = upload_id
        return client.post(
            '/dataset/upload_dataset',
            payload,
            HTTP_HOST='localhost',
        )

    def test_upload_session_is_persistent_and_owner_scoped(self):
        owner_client = Client(HTTP_HOST='localhost')
        owner_client.force_login(self.owner)
        first = self._chunk(owner_client, 0)
        self.assertEqual(first.status_code, 200)
        upload_id = first.json()['upload_id']
        session = UploadSession.objects.get(pk=upload_id)
        self.assertTrue(
            UploadPart.objects.filter(
                upload_session=session,
                chunk_number=0,
            ).exists()
        )

        other_client = Client(HTTP_HOST='localhost')
        other_client.force_login(self.other)
        denied = self._chunk(other_client, 1, upload_id)
        self.assertEqual(denied.status_code, 400)

        second = self._chunk(owner_client, 1, upload_id)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(session.parts.count(), 2)

        for part in session.parts.all():
            if default_storage.exists(part.storage_path):
                default_storage.delete(part.storage_path)
        session.delete()

    @patch('dataset.views.upload_to_user_bucket', return_value=(True, 'https://storage.test/file'))
    @patch('dataset.views.create_user_bucket', return_value=(True, 'bucket-test'))
    def test_finalize_creates_quarantined_version_and_source_asset(
        self,
        _create_bucket,
        _upload_file,
    ):
        owner_client = Client(HTTP_HOST='localhost')
        owner_client.force_login(self.owner)
        payload = {
            'chunkNumber': '0',
            'totalChunks': '1',
            'fileName': 'sample.csv',
            'fileSize': '1',
            'metadata': json.dumps({'dataset_name': 'Finalized upload'}),
            'file': SimpleUploadedFile('sample.csv', b'a'),
        }
        first = owner_client.post('/dataset/upload_dataset', payload)
        self.assertEqual(first.status_code, 200)
        upload_id = first.json()['upload_id']

        response = owner_client.post(
            f'/dataset/upload_dataset?finalize=true&uploadId={upload_id}',
        )

        self.assertEqual(response.status_code, 200)
        version = DatasetVersion.objects.get(dataset_id=response.json()['dataset_id'])
        asset = version.assets.get(kind='source')
        self.assertEqual(version.status, DatasetVersion.Status.PROCESSING)
        self.assertEqual(asset.byte_size, 1)
        self.assertTrue(PipelineRun.objects.filter(dataset_version=version, status='queued').exists())
        self.assertEqual(asset.sha256, 'ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb')

    def test_finalize_rejects_incomplete_upload(self):
        owner_client = Client(HTTP_HOST='localhost')
        owner_client.force_login(self.owner)
        first = self._chunk(owner_client, 0)
        upload_id = first.json()['upload_id']

        response = owner_client.post(
            f'/dataset/upload_dataset?finalize=true&uploadId={upload_id}',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            UploadSession.objects.get(pk=upload_id).status,
            UploadSession.Status.FAILED,
        )

    @patch('dataset.views.upload_to_user_bucket', return_value=(True, 'https://storage.test/file'))
    @patch('dataset.views.create_user_bucket', return_value=(True, 'bucket-test'))
    def test_batch_upload_groups_multiple_files_into_one_version(self, _create_bucket, _upload_file):
        owner_client = Client(HTTP_HOST='localhost')
        owner_client.force_login(self.owner)
        batch_response = owner_client.post(
            '/dataset/upload_batches',
            data=json.dumps({
                'metadata': {'dataset_name': 'Images', 'dataset_format': 'Image'},
                'files': [
                    {'name': 'one.jpg', 'relative_path': 'train/one.jpg', 'size': 1},
                    {'name': 'two.jpg', 'relative_path': 'train/two.jpg', 'size': 1},
                ],
            }),
            content_type='application/json',
        )
        self.assertEqual(batch_response.status_code, 200)
        batch_id = batch_response.json()['batch_id']

        for name, relative_path in (('one.jpg', 'train/one.jpg'), ('two.jpg', 'train/two.jpg')):
            first = owner_client.post('/dataset/upload_dataset', {
                'batchId': batch_id,
                'chunkNumber': '0',
                'totalChunks': '1',
                'fileName': name,
                'relativePath': relative_path,
                'fileSize': '1',
                'metadata': json.dumps({'relative_path': relative_path}),
                'file': SimpleUploadedFile(name, b'x'),
            })
            self.assertEqual(first.status_code, 200)
            finalize = owner_client.post(
                f"/dataset/upload_dataset?finalize=true&uploadId={first.json()['upload_id']}"
            )
            self.assertEqual(finalize.status_code, 200)

        batch = UploadBatch.objects.get(pk=batch_id)
        self.assertEqual(batch.status, UploadBatch.Status.PROCESSING)
        self.assertEqual(batch.completed_files, 2)
        self.assertEqual(batch.dataset.filesCount, 2)
        self.assertEqual(batch.dataset_version.assets.count(), 2)
        self.assertEqual(batch.dataset_version.pipeline_runs.count(), 1)
        access_response = owner_client.post(
            '/dataset/upload_batches/update',
            data=json.dumps({
                'batch_id': batch_id,
                'dataset_recordsNum': '42',
                'dataset_price': '12.50',
                'dataset_requestRequired': 'Yes',
            }),
            content_type='application/json',
        )
        self.assertEqual(access_response.status_code, 200)
        batch.dataset.refresh_from_db()
        self.assertEqual(batch.dataset.recordsNum, '42')
        self.assertEqual(str(batch.dataset.price), '12.50')
        self.assertEqual(batch.dataset.requestRequired, 'Yes')

    @patch('dataset.views.create_user_bucket', return_value=(True, 'bucket-test'))
    @patch('dataset.views.get_s3_client')
    def test_direct_multipart_upload_completes_without_local_parts(self, get_client, _create_bucket):
        client = MagicMock()
        client.create_multipart_upload.return_value = {'UploadId': 'multipart-1'}
        client.generate_presigned_url.return_value = 'https://storage.test/part'
        client.head_object.return_value = {'ContentLength': 1}
        client.get_object.return_value = {'Body': io.BytesIO(b'x')}
        get_client.return_value = client
        owner_client = Client(HTTP_HOST='localhost')
        owner_client.force_login(self.owner)
        batch_response = owner_client.post(
            '/dataset/upload_batches',
            data=json.dumps({
                'metadata': {'dataset_name': 'Direct images', 'dataset_format': 'Image'},
                'files': [{'name': 'one.jpg', 'relative_path': 'one.jpg', 'size': 1}],
            }),
            content_type='application/json',
        )
        batch_id = batch_response.json()['batch_id']
        create_response = owner_client.post(
            '/dataset/upload_direct/create',
            data=json.dumps({'batch_id': batch_id, 'file_name': 'one.jpg', 'relative_path': 'one.jpg', 'file_size': 1, 'content_type': 'image/jpeg'}),
            content_type='application/json',
        )
        self.assertEqual(create_response.status_code, 200)
        upload_id = create_response.json()['upload_id']
        part_response = owner_client.post(
            '/dataset/upload_direct/part-url',
            data=json.dumps({'upload_id': upload_id, 'part_number': 1}),
            content_type='application/json',
        )
        self.assertEqual(part_response.status_code, 200)
        abort_create_response = owner_client.post(
            '/dataset/upload_direct/create',
            data=json.dumps({'batch_id': batch_id, 'file_name': 'one.jpg', 'relative_path': 'one.jpg', 'file_size': 1, 'content_type': 'image/jpeg'}),
            content_type='application/json',
        )
        abort_upload_id = abort_create_response.json()['upload_id']
        abort_response = owner_client.post(
            '/dataset/upload_direct/abort',
            data=json.dumps({'upload_id': abort_upload_id}),
            content_type='application/json',
        )
        self.assertEqual(abort_response.status_code, 200)
        self.assertEqual(UploadSession.objects.get(pk=abort_upload_id).status, UploadSession.Status.FAILED)
        client.abort_multipart_upload.assert_called()
        complete_response = owner_client.post(
            '/dataset/upload_direct/complete',
            data=json.dumps({'upload_id': upload_id, 'parts': [{'part_number': 1, 'etag': '"etag-1"'}]}),
            content_type='application/json',
        )
        self.assertEqual(complete_response.status_code, 200)
        self.assertEqual(complete_response.json()['completed_files'], 1)
        self.assertFalse(UploadPart.objects.exists())
        self.assertEqual(DatasetAsset.objects.filter(original_name='one.jpg').count(), 1)


class DatasetWorkflowTemplateTests(TestCase):
    def test_five_stage_workflow_renders(self):
        user = User.objects.create_user('workflow-owner')
        client = Client(HTTP_HOST='localhost')
        client.force_login(user)
        response = client.get('/dataset/dataset_define_stepper')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dataset-workflow')
        self.assertContains(response, 'createBatchUrl')
        self.assertContains(response, 'directCreateUrl')
        self.assertContains(response, 'directAbortUrl')
        self.assertContains(response, 'directUploadFallback')
        self.assertContains(response, 'dataset_folder')
        self.assertContains(response, 'aria-controls="dataset_file"')
        self.assertContains(response, 'workflow-file-input')

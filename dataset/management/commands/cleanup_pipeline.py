from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from dataset.models import PipelineRun, UploadBatch, UploadSession
from dataset.views import cleanup_upload


class Command(BaseCommand):
    help = 'Expire abandoned uploads and requeue stale pipeline runs.'

    def handle(self, *args, **options):
        now = timezone.now()
        expired_batches = UploadBatch.objects.filter(
            expires_at__lte=now,
            status__in=[UploadBatch.Status.CREATED, UploadBatch.Status.UPLOADING],
        ).update(status=UploadBatch.Status.EXPIRED)
        expired_sessions = list(
            UploadSession.objects.filter(
                expires_at__lte=now,
                status__in=[UploadSession.Status.CREATED, UploadSession.Status.UPLOADING],
            ).values_list('id', flat=True)
        )
        for session_id in expired_sessions:
            cleanup_upload(session_id, status=UploadSession.Status.EXPIRED)

        stale_before = now - timedelta(seconds=settings.PIPELINE_RUN_STALE_AFTER_SECONDS)
        with transaction.atomic():
            stale_runs = PipelineRun.objects.select_for_update().filter(
                status=PipelineRun.Status.RUNNING,
                started_at__lte=stale_before,
            )
            stale_count = stale_runs.update(
                status=PipelineRun.Status.QUEUED,
                finished_at=None,
            )
        self.stdout.write(
            self.style.SUCCESS(
                f'expired_batches={expired_batches} expired_sessions={len(expired_sessions)} stale_runs_requeued={stale_count}'
            )
        )

import uuid

from django.conf import settings
from django.db import models

from dataset.models import Dataset


class ProviderImportRequest(models.Model):
    """GUI-side audit record for a job owned by the connector service."""

    class Provider(models.TextChoices):
        HUGGINGFACE = 'huggingface', 'Hugging Face'
        KAGGLE = 'kaggle', 'Kaggle'

    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        RUNNING = 'running', 'Running'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'
        UNKNOWN = 'unknown', 'Unknown'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    api_job_id = models.UUIDField(null=True, blank=True, unique=True)
    request_key = models.CharField(max_length=255, unique=True)
    provider = models.CharField(max_length=20, choices=Provider.choices)
    provider_dataset_id = models.CharField(max_length=500)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='provider_import_requests',
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='requested_provider_imports',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    error_code = models.CharField(max_length=120, blank=True)
    gui_dataset_id = models.PositiveBigIntegerField(null=True, blank=True)
    gui_dataset_version_id = models.PositiveBigIntegerField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('status', 'created_at')),
            models.Index(fields=('provider', 'created_at')),
        ]

    @property
    def dataset(self):
        if not self.gui_dataset_id:
            return None
        return Dataset.objects.filter(pk=self.gui_dataset_id).first()

    def __str__(self):
        return f'{self.provider}:{self.provider_dataset_id}'

from django.contrib.auth.models import User
from django.db import models
import uuid
from taggit.managers import TaggableManager



class BlockUser(models.Model):
    username = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.username

class InternationalDataset(models.Model):
    CREATE_TYPE = (
        ('Create', 'Create'),
        ('Transfer', 'Transfer')
    )

    DATA_TYPE = (
        ('Text', 'Text'),
        ('Image', 'Image'),
        ('Audio', 'Audio'),
        ('Video', 'Video'),
        ('GeoData', 'GeoData')
    )

    DATASET_STATUS = (
        ('Initialized', 'Initialized'),
        ('Download_Progress', 'Download_Progress'),
        ('Download_Failed', 'Download_Failed'),
        ('Download_Completed', 'Download_Completed'),
        ('Transfer', 'Transfer')
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='international_datasets', blank=True, null=True)
    code = models.CharField(max_length=100, blank=True, null=True)
    name = models.CharField(max_length=1000, blank=True, null=True)
    owner = models.CharField(max_length=1000, blank=True, null=True)
    internalId = models.CharField(max_length=300, blank=True, null=True)
    internalCode = models.CharField(max_length=300, blank=True, null=True)
    recordsNum = models.CharField(max_length=10, blank=True, null=True)
    size = models.CharField(max_length=30, blank=True, null=True)
    format = models.CharField(max_length=100, blank=True, null=True)
    language = models.CharField(max_length=30, blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    license = models.CharField(max_length=100, blank=True, null=True)
    tasks = models.CharField(max_length=1000, blank=True, null=True)
    datasetDate = models.DateTimeField(blank=True, null=True)
    columnDataType = models.JSONField(blank=True, null=True)
    sourceJson = models.JSONField(blank=True, null=True)
    image = models.ImageField(upload_to='images', blank=True, null=True)
    refDownloadLink = models.JSONField(blank=True, null=True)
    downloadLink = models.JSONField(blank=True, null=True)
    price = models.FloatField(blank=True, null=True)
    createType = models.CharField(max_length=50, choices=CREATE_TYPE, default='Transfer', blank=True, null=True)
    referenceOwner = models.CharField(max_length=500, blank=True, null=True)
    datasetRate = models.FloatField(blank=True, null=True)
    dataType = models.CharField(max_length=50, blank=True, null=True)
    dataset_tags = models.TextField(blank=True, null=True)
    likes = models.IntegerField(blank=True, null=True)
    downloads = models.IntegerField(blank=True, null=True)
    dataset_status = models.CharField(max_length=200, choices=DATASET_STATUS, default='Initialized', blank=True, null=True)
    filesCount = models.IntegerField(blank=True, null=True)
    refLink = models.TextField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name[:50]


class Dataset(models.Model):
    CREATE_TYPE = (
        ('Create', 'Create'),
        ('Transfer', 'Transfer')
    )

    DATA_TYPE = (
        ('Text', 'Text'),
        ('Image', 'Image'),
        ('Audio', 'Audio'),
        ('Video', 'Video'),
        ('GeoData', 'GeoData')
    )

    REQUEST_REQUIRED = (
        ('Yes', 'Yes'),
        ('No', 'No')
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='datasets', blank=True, null=True)
    organization = models.ForeignKey(
        'account.Organization',
        on_delete=models.PROTECT,
        related_name='datasets',
        blank=True,
        null=True,
    )
    code = models.CharField(max_length=100, blank=True, null=True)
    name = models.CharField(max_length=1000, blank=True, null=True)
    owner = models.CharField(max_length=1000, blank=True, null=True)
    internalId = models.CharField(max_length=300, blank=True, null=True)
    internalCode = models.CharField(max_length=300, blank=True, null=True)
    recordsNum = models.CharField(max_length=10, blank=True, null=True)
    size = models.CharField(max_length=30, blank=True, null=True)
    format = models.CharField(max_length=30, blank=True, null=True)
    language = models.CharField(max_length=30, blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    license = models.CharField(max_length=100, blank=True, null=True)
    tasks = models.CharField(max_length=1000, blank=True, null=True)
    datasetDate = models.DateTimeField(blank=True, null=True)
    columnDataType = models.JSONField(blank=True, null=True)
    image = models.ImageField(upload_to='images', blank=True, null=True)
    requestRequired = models.CharField(max_length=50, choices=REQUEST_REQUIRED, default='No', blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=(
            ('draft', 'Draft'),
            ('uploading', 'Uploading'),
            ('quarantined', 'Quarantined'),
            ('processing', 'Processing'),
            ('needs_review', 'Needs review'),
            ('published', 'Published'),
            ('rejected', 'Rejected'),
            ('failed', 'Failed'),
            ('archived', 'Archived'),
        ),
        default='draft',
    )
    downloadLink = models.JSONField(blank=True, null=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0, blank=True)
    downloadCount = models.IntegerField(blank=True, null=True)
    referenceOwner = models.CharField(max_length=500, blank=True, null=True)
    createType = models.CharField(max_length=50, choices=CREATE_TYPE, default='Create', blank=True, null=True)
    datasetRate = models.FloatField(blank=True, null=True)
    dataType = models.CharField(max_length=50, choices=DATA_TYPE, default='Text', blank=True, null=True)
    dataset_tags = models.TextField(blank=True, null=True)
    tags = TaggableManager()
    likes = models.ManyToManyField(User, related_name='likes', blank=True)
    filesCount = models.IntegerField(blank=True, null=True)
    refLink = models.TextField(blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)

    def total_likes(self):
        return self.likes.count()
    def __str__(self):
        return self.name[:50]


class Comment(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    text = models.TextField()
    sentiment_model = models.CharField(max_length=200, blank=True, null=True)
    sentiment_label = models.CharField(max_length=10, blank=True, null=True)
    sentiment_score = models.FloatField(blank=True, null=True)
    Date = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.text[:30]


class PredefinedTag(models.Model):
    tag = models.CharField(max_length=2000, blank=True, null=True)
    scope = models.CharField(max_length=2000, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.tag[:30]

class Product(models.Model):
    TYPE = (
        ('Paper', 'Paper'),
        ('Model', 'Model'),
        ('Service', 'Service'),
        ('Code', 'Code')
    )
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="products")
    title = models.CharField(max_length=1000, blank=True, null=True)
    type = models.CharField(max_length=200, choices=TYPE, default='Paper', blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    productDate = models.DateField(blank=True, null=True)
    link = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='products', blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title[:30]


class Request(models.Model):
    RESPONSE_TYPE = (
        ('Request', 'Request'),
        ('Accept', 'Accept'),
        ('Reject', 'Reject')
    )
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="requests")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="requests")
    text = models.TextField(blank=True, null=True)
    responseType = models.CharField(max_length=50, choices=RESPONSE_TYPE, default='Request', blank=True, null=True)
    requestDate = models.DateTimeField(auto_now_add=True)
    responseDate = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.text[:30]


class AnnotationRequest(models.Model):
    PRICE_TYPE = (
        ('Free', 'Free'),
        ('Pricing', 'Pricing')
    )
    ANNOTATION_STATUS = (
        ('Requested', 'Requested'),
        ('Accepted', 'Accepted'),
        ('Completed', 'Completed'),
        ('Payed', 'Payed'),
        ('Canceled', 'Canceled')
    )
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="annotation_requests")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="annotation_requests", blank=True, null=True)
    priceType = models.CharField(max_length=50, choices=PRICE_TYPE, default='Pricing', blank=True, null=True)
    estimatedPrice = models.FloatField(blank=True, null=True)
    finalPrice = models.FloatField(blank=True, null=True)
    totalFinalPrice = models.FloatField(blank=True, null=True)
    startRecord = models.FloatField(blank=True, null=True)
    endRecord = models.FloatField(blank=True, null=True)
    totalRecords = models.FloatField(blank=True, null=True)
    requestDateTime = models.DateTimeField(auto_now_add=True)
    responseDateTime = models.DateTimeField(blank=True, null=True)
    completeDateTime = models.DateTimeField(blank=True, null=True)
    duration = models.FloatField(blank=True, null=True)
    annotationStatus = models.CharField(max_length=50, choices=ANNOTATION_STATUS, default='Requested', blank=True, null=True)
    labelOptions = models.JSONField(blank=True, null=True)
    labelResults = models.JSONField(blank=True, null=True)
    desc = models.TextField(blank=True, null=True)
    tags = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.desc[:30]


class AnnotationResponse(models.Model):
    RESPONSE_TYPE = (
        ('Request', 'Request'),
        ('Accept', 'Accept'),
        ('Reject', 'Reject'),
        ('Cancel', 'Cancel')
    )
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="annotation_responses")
    annotationRequest = models.ForeignKey(AnnotationRequest, on_delete=models.CASCADE, related_name="annotation_responses")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="annotation_responses")
    text = models.TextField(blank=True, null=True)
    responseType = models.CharField(max_length=50, choices=RESPONSE_TYPE, default='Request', blank=True, null=True)
    responseDate = models.DateTimeField(blank=True, null=True)
    suggestedPrice = models.FloatField(blank=True, null=True)

    def __str__(self):
        return self.text[:30]


class DatasetVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PROCESSING = 'processing', 'Processing'
        NEEDS_REVIEW = 'needs_review', 'Needs review'
        PUBLISHED = 'published', 'Published'
        FAILED = 'failed', 'Failed'
        ARCHIVED = 'archived', 'Archived'

    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name='versions',
    )
    version = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    pipeline_definition_version = models.CharField(max_length=120, blank=True)
    checksum_manifest = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='created_dataset_versions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(blank=True, null=True)
    published_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='published_dataset_versions',
        blank=True,
        null=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('dataset', 'version'),
                name='unique_dataset_version',
            ),
        ]
        ordering = ('dataset_id', '-version')

    def __str__(self):
        return f'{self.dataset_id}.v{self.version}'


class DatasetAsset(models.Model):
    class Kind(models.TextChoices):
        SOURCE = 'source', 'Source'
        DERIVED = 'derived', 'Derived'
        PREVIEW = 'preview', 'Preview'
        REPORT = 'report', 'Report'

    dataset_version = models.ForeignKey(
        DatasetVersion,
        on_delete=models.CASCADE,
        related_name='assets',
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    object_key = models.CharField(max_length=1024)
    storage_bucket = models.CharField(max_length=255, blank=True)
    original_name = models.CharField(max_length=255, blank=True)
    relative_path = models.CharField(max_length=2048, blank=True)
    media_type = models.CharField(max_length=255, blank=True)
    byte_size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, default='quarantined')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('dataset_version', 'object_key'),
                name='unique_dataset_asset_key',
            ),
        ]
        indexes = [
            models.Index(fields=('dataset_version', 'kind')),
            models.Index(fields=('sha256',)),
        ]

    def __str__(self):
        return self.object_key


class ExternalImportReceipt(models.Model):
    """Idempotency receipt for an import completed by a trusted connector."""

    class Provider(models.TextChoices):
        HUGGINGFACE = 'huggingface', 'Hugging Face'
        KAGGLE = 'kaggle', 'Kaggle'

    request_key = models.CharField(max_length=255, unique=True)
    payload_sha256 = models.CharField(max_length=64)
    provider = models.CharField(max_length=20, choices=Provider.choices)
    external_dataset_id = models.CharField(max_length=500)
    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.PROTECT,
        related_name='external_imports',
    )
    dataset_version = models.OneToOneField(
        DatasetVersion,
        on_delete=models.PROTECT,
        related_name='external_import_receipt',
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='external_dataset_imports',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.provider}:{self.external_dataset_id}'


class PipelineDefinition(models.Model):
    name = models.CharField(max_length=120)
    version = models.CharField(max_length=40)
    definition = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('name', 'version'),
                name='unique_pipeline_definition_version',
            ),
        ]
        ordering = ('name', '-created_at')

    def __str__(self):
        return f'{self.name}:{self.version}'


class PipelineRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = 'queued', 'Queued'
        RUNNING = 'running', 'Running'
        SUCCEEDED = 'succeeded', 'Succeeded'
        NEEDS_REVIEW = 'needs_review', 'Needs review'
        FAILED = 'failed', 'Failed'

    dataset_version = models.ForeignKey(
        DatasetVersion,
        on_delete=models.CASCADE,
        related_name='pipeline_runs',
    )
    pipeline_definition = models.ForeignKey(
        PipelineDefinition,
        on_delete=models.PROTECT,
        related_name='runs',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    idempotency_key = models.CharField(max_length=160, unique=True)
    input_manifest = models.JSONField(default=dict, blank=True)
    output_manifest = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=120, blank=True)
    requested_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='requested_pipeline_runs',
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('dataset_version', 'pipeline_definition'),
                name='unique_pipeline_run_definition',
            ),
        ]
        indexes = [
            models.Index(fields=('status', 'created_at')),
        ]

    def __str__(self):
        return f'{self.dataset_version_id}:{self.pipeline_definition_id}'


class PipelineStepRun(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Failed'

    pipeline_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.CASCADE,
        related_name='steps',
    )
    step_key = models.CharField(max_length=120)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    attempt = models.PositiveIntegerField(default=0)
    metrics = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=120, blank=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('pipeline_run', 'step_key'),
                name='unique_pipeline_step',
            ),
        ]
        ordering = ('pipeline_run_id', 'id')


class QualityReport(models.Model):
    class Result(models.TextChoices):
        PASS = 'pass', 'Pass'
        REVIEW = 'review', 'Review'
        FAIL = 'fail', 'Fail'

    dataset_version = models.OneToOneField(
        DatasetVersion,
        on_delete=models.CASCADE,
        related_name='quality_report',
    )
    result = models.CharField(max_length=20, choices=Result.choices)
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
    )
    metrics = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class UploadBatch(models.Model):
    class Status(models.TextChoices):
        CREATED = 'created', 'Created'
        UPLOADING = 'uploading', 'Uploading'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        EXPIRED = 'expired', 'Expired'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='dataset_upload_batches',
    )
    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name='upload_batches',
    )
    dataset_version = models.OneToOneField(
        DatasetVersion,
        on_delete=models.CASCADE,
        related_name='upload_batch',
    )
    expected_files = models.PositiveIntegerField(default=1)
    completed_files = models.PositiveIntegerField(default=0)
    expected_bytes = models.PositiveBigIntegerField(default=0)
    completed_bytes = models.PositiveBigIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=('owner', 'status'), name='dataset_upl_owner__b1e9bc_idx'),
            models.Index(fields=('expires_at',), name='dataset_upl_expires_5fd8ab_idx'),
        ]

    def __str__(self):
        return f'{self.owner_id}:{self.id}'


class UploadSession(models.Model):
    class Status(models.TextChoices):
        CREATED = 'created', 'Created'
        UPLOADING = 'uploading', 'Uploading'
        ASSEMBLING = 'assembling', 'Assembling'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        EXPIRED = 'expired', 'Expired'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='upload_sessions',
    )
    batch = models.ForeignKey(
        'UploadBatch',
        on_delete=models.CASCADE,
        related_name='upload_sessions',
        blank=True,
        null=True,
    )
    file_name = models.CharField(max_length=255)
    multipart_upload_id = models.CharField(max_length=255, blank=True)
    storage_bucket = models.CharField(max_length=255, blank=True)
    object_key = models.CharField(max_length=1024, blank=True)
    expected_size = models.PositiveBigIntegerField(default=0)
    total_chunks = models.PositiveIntegerField()
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=('owner', 'status')),
            models.Index(fields=('expires_at',)),
            models.Index(fields=('batch', 'status'), name='dataset_upl_batch_i_2c7b51_idx'),
        ]

    def __str__(self):
        return f'{self.owner_id}:{self.id}'


class UploadPart(models.Model):
    upload_session = models.ForeignKey(
        UploadSession,
        on_delete=models.CASCADE,
        related_name='parts',
    )
    chunk_number = models.PositiveIntegerField()
    storage_path = models.CharField(max_length=1024)
    byte_size = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('upload_session', 'chunk_number'),
                name='unique_upload_part',
            ),
        ]
        ordering = ('chunk_number',)

    def __str__(self):
        return f'{self.upload_session_id}:{self.chunk_number}'

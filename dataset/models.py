from django.contrib.auth.models import User
from django.db import models
from taggit.managers import TaggableManager



class BlockUser(models.Model):
    username = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.username


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
    sourceJson = models.JSONField(blank=True, null=True)
    image = models.ImageField(upload_to='images', blank=True, null=True)
    requestRequired = models.CharField(max_length=50, choices=REQUEST_REQUIRED, default='No', blank=True, null=True)
    downloadLink = models.JSONField(blank=True, null=True)
    price = models.FloatField(blank=True, null=True)
    downloadCount = models.IntegerField(blank=True, null=True)
    referenceOwner = models.CharField(max_length=500, blank=True, null=True)
    createType = models.CharField(max_length=50, choices=CREATE_TYPE, default='Create', blank=True, null=True)
    datasetRate = models.FloatField(blank=True, null=True)
    dataType = models.CharField(max_length=50, choices=DATA_TYPE, default='Text', blank=True, null=True)
    dataset_tags = models.TextField(blank=True, null=True)
    tags = TaggableManager()
    likes = models.ManyToManyField(User, related_name='likes', blank=True, null=True)
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

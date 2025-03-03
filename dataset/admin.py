from django.contrib import admin
from . import models

admin.site.register(models.BlockUser)

admin.site.register(models.Dataset)
admin.site.register(models.Comment)
admin.site.register(models.PredefinedTag)
admin.site.register(models.Product)
admin.site.register(models.Request)
admin.site.register(models.AnnotationRequest)
admin.site.register(models.AnnotationResponse)


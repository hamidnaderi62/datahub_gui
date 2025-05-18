from django.db import models
from django.contrib.auth.models import User


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="profiles/images", blank=True, null=True)
    code = models.CharField(max_length=10, blank=True, null=True)
    name = models.CharField(max_length=500, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    site = models.TextField(blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    profile_tags = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.user.username


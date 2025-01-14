from django.db import models
from django.contrib.auth.models import User


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="profiles/images", blank=True, null=True)
    code = models.CharField(max_length=10)

    def __str__(self):
        return self.user.username


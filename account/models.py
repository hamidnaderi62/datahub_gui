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



class Organization(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        SUSPENDED = 'suspended', 'Suspended'

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=120, unique=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        ADMIN = 'admin', 'Admin'
        PUBLISHER = 'publisher', 'Publisher'
        BUYER = 'buyer', 'Buyer'
        VIEWER = 'viewer', 'Viewer'

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='organization_memberships',
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('organization', 'user'),
                name='unique_organization_membership',
            ),
        ]

    def __str__(self):
        return f'{self.organization.slug}:{self.user.username}'

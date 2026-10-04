import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dataset', '0009_externalimportreceipt'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='datasetasset',
            name='relative_path',
            field=models.CharField(blank=True, max_length=2048),
        ),
        migrations.CreateModel(
            name='UploadBatch',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('expected_files', models.PositiveIntegerField(default=1)),
                ('completed_files', models.PositiveIntegerField(default=0)),
                ('expected_bytes', models.PositiveBigIntegerField(default=0)),
                ('completed_bytes', models.PositiveBigIntegerField(default=0)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('status', models.CharField(choices=[('created', 'Created'), ('uploading', 'Uploading'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed'), ('expired', 'Expired')], default='created', max_length=20)),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('dataset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='upload_batches', to='dataset.dataset')),
                ('dataset_version', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='upload_batch', to='dataset.datasetversion')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dataset_upload_batches', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'indexes': [
                    models.Index(fields=['owner', 'status'], name='dataset_upl_owner__b1e9bc_idx'),
                    models.Index(fields=['expires_at'], name='dataset_upl_expires_5fd8ab_idx'),
                ],
            },
        ),
        migrations.AddField(
            model_name='uploadsession',
            name='batch',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='upload_sessions', to='dataset.uploadbatch'),
        ),
        migrations.AddIndex(
            model_name='uploadsession',
            index=models.Index(fields=['batch', 'status'], name='dataset_upl_batch_i_2c7b51_idx'),
        ),
    ]

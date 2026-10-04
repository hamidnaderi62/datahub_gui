import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0002_organization_membership'),
        ('dataset', '0004_alter_dataset_price_decimal'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='dataset',
            name='organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='datasets', to='account.organization'),
        ),
        migrations.AddField(
            model_name='dataset',
            name='status',
            field=models.CharField(choices=[('draft', 'Draft'), ('uploading', 'Uploading'), ('quarantined', 'Quarantined'), ('processing', 'Processing'), ('needs_review', 'Needs review'), ('published', 'Published'), ('rejected', 'Rejected'), ('failed', 'Failed'), ('archived', 'Archived')], default='draft', max_length=20),
        ),
        migrations.CreateModel(
            name='DatasetVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.PositiveIntegerField()),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('processing', 'Processing'), ('needs_review', 'Needs review'), ('published', 'Published'), ('failed', 'Failed'), ('archived', 'Archived')], default='draft', max_length=20)),
                ('pipeline_definition_version', models.CharField(blank=True, max_length=120)),
                ('checksum_manifest', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_dataset_versions', to=settings.AUTH_USER_MODEL)),
                ('dataset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='versions', to='dataset.dataset')),
            ],
            options={
                'ordering': ('dataset_id', '-version'),
            },
        ),
        migrations.CreateModel(
            name='DatasetAsset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('source', 'Source'), ('derived', 'Derived'), ('preview', 'Preview'), ('report', 'Report')], max_length=20)),
                ('object_key', models.CharField(max_length=1024)),
                ('original_name', models.CharField(blank=True, max_length=255)),
                ('media_type', models.CharField(blank=True, max_length=255)),
                ('byte_size', models.PositiveBigIntegerField(default=0)),
                ('sha256', models.CharField(blank=True, max_length=64)),
                ('status', models.CharField(default='quarantined', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('dataset_version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assets', to='dataset.datasetversion')),
            ],
        ),
        migrations.CreateModel(
            name='UploadSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('file_name', models.CharField(max_length=255)),
                ('expected_size', models.PositiveBigIntegerField(default=0)),
                ('total_chunks', models.PositiveIntegerField()),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('status', models.CharField(choices=[('created', 'Created'), ('uploading', 'Uploading'), ('assembling', 'Assembling'), ('completed', 'Completed'), ('failed', 'Failed'), ('expired', 'Expired')], default='created', max_length=20)),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='upload_sessions', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='UploadPart',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('chunk_number', models.PositiveIntegerField()),
                ('storage_path', models.CharField(max_length=1024)),
                ('byte_size', models.PositiveBigIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('upload_session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='parts', to='dataset.uploadsession')),
            ],
            options={
                'ordering': ('chunk_number',),
            },
        ),
        migrations.AddConstraint(
            model_name='datasetversion',
            constraint=models.UniqueConstraint(fields=('dataset', 'version'), name='unique_dataset_version'),
        ),
        migrations.AddIndex(
            model_name='datasetasset',
            index=models.Index(fields=['dataset_version', 'kind'], name='dataset_dat_dataset_6bdb76_idx'),
        ),
        migrations.AddIndex(
            model_name='datasetasset',
            index=models.Index(fields=['sha256'], name='dataset_dat_sha256_fecfa4_idx'),
        ),
        migrations.AddConstraint(
            model_name='datasetasset',
            constraint=models.UniqueConstraint(fields=('dataset_version', 'object_key'), name='unique_dataset_asset_key'),
        ),
        migrations.AddIndex(
            model_name='uploadsession',
            index=models.Index(fields=['owner', 'status'], name='dataset_upl_owner_i_2deefa_idx'),
        ),
        migrations.AddIndex(
            model_name='uploadsession',
            index=models.Index(fields=['expires_at'], name='dataset_upl_expires_996376_idx'),
        ),
        migrations.AddConstraint(
            model_name='uploadpart',
            constraint=models.UniqueConstraint(fields=('upload_session', 'chunk_number'), name='unique_upload_part'),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dataset', '0010_uploadbatch_asset_path'),
    ]

    operations = [
        migrations.AddField(
            model_name='uploadsession',
            name='multipart_upload_id',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='uploadsession',
            name='object_key',
            field=models.CharField(blank=True, max_length=1024),
        ),
        migrations.AddField(
            model_name='uploadsession',
            name='storage_bucket',
            field=models.CharField(blank=True, max_length=255),
        ),
    ]

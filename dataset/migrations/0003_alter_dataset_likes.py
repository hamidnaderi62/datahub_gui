from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dataset', '0002_alter_dataset_price'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dataset',
            name='likes',
            field=models.ManyToManyField(
                blank=True,
                related_name='likes',
                to='auth.user',
            ),
        ),
    ]

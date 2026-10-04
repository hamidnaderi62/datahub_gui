from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dataset', '0003_alter_dataset_likes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dataset',
            name='price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                max_digits=12,
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("manuscript", "0004_sps_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="manuscript",
            name="front_counts",
            field=models.JSONField(
                blank=True, default=dict, verbose_name="Front counts"
            ),
        ),
    ]

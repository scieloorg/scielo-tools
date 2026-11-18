from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("manuscript", "0008_manuscriptfigurefile_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="manuscriptmarkingrun",
            name="endpoints",
            field=models.CharField(
                blank=True, max_length=16, verbose_name="Endpoints"
            ),
        ),
    ]

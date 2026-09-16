from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("front", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="front",
            name="normalized_text",
            field=models.TextField(blank=True, verbose_name="Normalized text"),
        ),
    ]

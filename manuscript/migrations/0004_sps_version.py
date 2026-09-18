from django.db import migrations, models


def set_specific_use_to_sps_1_10(apps, schema_editor):
    Manuscript = apps.get_model("manuscript", "Manuscript")
    Manuscript.objects.filter(specific_use="sps-1.9").update(specific_use="sps-1.10")


class Migration(migrations.Migration):
    dependencies = [
        ("manuscript", "0003_originallanguage"),
    ]

    operations = [
        migrations.AlterField(
            model_name="manuscript",
            name="specific_use",
            field=models.CharField(
                default="sps-1.10",
                max_length=32,
                verbose_name="SPS version",
            ),
        ),
        migrations.RunPython(set_specific_use_to_sps_1_10, migrations.RunPython.noop),
    ]

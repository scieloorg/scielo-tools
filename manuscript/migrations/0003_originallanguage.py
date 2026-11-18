from django.db import migrations, models

from manuscript.sps_languages import SPS_ORIGINAL_LANGUAGES


def populate_original_languages(apps, schema_editor):
    OriginalLanguage = apps.get_model("manuscript", "OriginalLanguage")
    for sort_order, (code, name) in enumerate(SPS_ORIGINAL_LANGUAGES):
        OriginalLanguage.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "sort_order": sort_order,
            },
        )


def remove_seeded_original_languages(apps, schema_editor):
    OriginalLanguage = apps.get_model("manuscript", "OriginalLanguage")
    OriginalLanguage.objects.filter(
        code__in=[code for code, _name in SPS_ORIGINAL_LANGUAGES]
    ).delete()


def set_empty_language_to_pt(apps, schema_editor):
    Manuscript = apps.get_model("manuscript", "Manuscript")
    Manuscript.objects.filter(language="").update(language="pt")


class Migration(migrations.Migration):
    dependencies = [
        ("manuscript", "0002_articletype"),
    ]

    operations = [
        migrations.CreateModel(
            name="OriginalLanguage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "code",
                    models.CharField(max_length=16, unique=True, verbose_name="Code"),
                ),
                ("name", models.CharField(max_length=128, verbose_name="Name")),
                (
                    "sort_order",
                    models.PositiveIntegerField(default=0, verbose_name="Sort order"),
                ),
            ],
            options={
                "verbose_name": "Original language",
                "verbose_name_plural": "Original languages",
                "ordering": ["sort_order", "code"],
            },
        ),
        migrations.AlterField(
            model_name="manuscript",
            name="language",
            field=models.CharField(
                default="pt",
                help_text="Closed list of ISO 639-1 codes for the article original language.",
                max_length=16,
                verbose_name="Original language",
            ),
        ),
        migrations.RunPython(
            populate_original_languages, remove_seeded_original_languages
        ),
        migrations.RunPython(set_empty_language_to_pt, migrations.RunPython.noop),
    ]

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Front",
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
                ("source_text", models.TextField(verbose_name="Source text")),
                (
                    "normalized_text",
                    models.TextField(
                        blank=True, db_index=True, verbose_name="Normalized text"
                    ),
                ),
                (
                    "checksum",
                    models.CharField(
                        blank=True, max_length=64, unique=True, verbose_name="SHA256"
                    ),
                ),
                (
                    "marked",
                    models.JSONField(blank=True, default=dict, verbose_name="Marked"),
                ),
                ("marked_xml", models.TextField(blank=True, verbose_name="Marked XML")),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Creation date"
                    ),
                ),
                (
                    "updated",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Last update date"
                    ),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_creator",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Creator",
                    ),
                ),
            ],
            options={
                "verbose_name": "Front",
                "verbose_name_plural": "Fronts",
            },
        ),
    ]

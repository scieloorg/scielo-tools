import django.core.validators
import django.db.models.deletion
import modelcluster.fields
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("wagtaildocs", "0014_alter_document_file_size"),
        ("xml_manager", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Manuscript",
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
                ("title", models.CharField(max_length=512, verbose_name="Title")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("front", "Front"),
                            ("body", "Body"),
                            ("back", "Back"),
                            ("assembled", "Assembled"),
                            ("validated", "Validated"),
                            ("ready", "Ready"),
                            ("published", "Published"),
                        ],
                        default="draft",
                        max_length=16,
                        verbose_name="Status",
                    ),
                ),
                (
                    "article_type",
                    models.CharField(
                        default="research-article",
                        max_length=64,
                        verbose_name="Article type",
                    ),
                ),
                (
                    "language",
                    models.CharField(
                        blank=True, default="", max_length=16, verbose_name="Language"
                    ),
                ),
                (
                    "specific_use",
                    models.CharField(
                        default="sps-1.9", max_length=32, verbose_name="Specific use"
                    ),
                ),
                (
                    "front_source_text",
                    models.TextField(blank=True, verbose_name="Front source text"),
                ),
                (
                    "front_marked",
                    models.JSONField(
                        blank=True, default=dict, verbose_name="Front marked"
                    ),
                ),
                (
                    "front_marked_xml",
                    models.TextField(blank=True, verbose_name="Front marked XML"),
                ),
                (
                    "body_source_text",
                    models.TextField(blank=True, verbose_name="Body source text"),
                ),
                (
                    "body_marked",
                    models.JSONField(
                        blank=True, default=dict, verbose_name="Body marked"
                    ),
                ),
                (
                    "body_marked_xml",
                    models.TextField(blank=True, verbose_name="Body marked XML"),
                ),
                (
                    "body_tables",
                    models.JSONField(
                        blank=True, default=list, verbose_name="Body tables"
                    ),
                ),
                (
                    "body_figures",
                    models.JSONField(
                        blank=True, default=list, verbose_name="Body figures"
                    ),
                ),
                (
                    "references_source_text",
                    models.TextField(blank=True, verbose_name="References source text"),
                ),
                (
                    "assembled_xml",
                    models.TextField(blank=True, verbose_name="Assembled XML"),
                ),
                (
                    "front_approved_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Front approved at"
                    ),
                ),
                (
                    "body_approved_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Body approved at"
                    ),
                ),
                (
                    "back_approved_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Back approved at"
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(auto_now_add=True, verbose_name="Created"),
                ),
                (
                    "updated",
                    models.DateTimeField(auto_now=True, verbose_name="Updated"),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="manuscripts_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Creator",
                    ),
                ),
                (
                    "source_document",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="manuscripts",
                        to="wagtaildocs.document",
                        verbose_name="Source DOCX",
                    ),
                ),
                (
                    "sps_package",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="manuscript_sps_packages",
                        to="wagtaildocs.document",
                        verbose_name="SPS package",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="manuscripts_updated",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Updated by",
                    ),
                ),
                (
                    "validation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="manuscripts",
                        to="xml_manager.spspackagevalidation",
                        verbose_name="Validation",
                    ),
                ),
            ],
            options={
                "verbose_name": "Manuscript",
                "verbose_name_plural": "Manuscripts",
                "ordering": ["-updated"],
            },
        ),
        migrations.CreateModel(
            name="ManuscriptPublication",
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
                    "external_id",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="External ID"
                    ),
                ),
                (
                    "preview_url",
                    models.URLField(blank=True, verbose_name="Preview URL"),
                ),
                (
                    "published_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Published at"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        default="pending", max_length=32, verbose_name="Status"
                    ),
                ),
                (
                    "manuscript",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="publications",
                        to="manuscript.manuscript",
                        verbose_name="Manuscript",
                    ),
                ),
            ],
            options={
                "verbose_name": "Manuscript publication",
                "verbose_name_plural": "Manuscript publications",
            },
        ),
        migrations.CreateModel(
            name="ManuscriptReference",
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
                    "sort_order",
                    models.IntegerField(blank=True, editable=False, null=True),
                ),
                (
                    "mixed_citation",
                    models.TextField(blank=True, verbose_name="Mixed citation"),
                ),
                (
                    "marked",
                    models.JSONField(blank=True, default=dict, verbose_name="Marked"),
                ),
                (
                    "marked_xml",
                    models.TextField(blank=True, verbose_name="Marked XML"),
                ),
                (
                    "score",
                    models.IntegerField(
                        blank=True,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(10),
                        ],
                    ),
                ),
                (
                    "manuscript",
                    modelcluster.fields.ParentalKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="references",
                        to="manuscript.manuscript",
                    ),
                ),
            ],
            options={
                "verbose_name": "Manuscript reference",
                "verbose_name_plural": "Manuscript references",
                "ordering": ["sort_order"],
            },
        ),
    ]

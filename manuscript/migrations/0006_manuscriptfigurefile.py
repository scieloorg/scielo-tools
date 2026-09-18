import django.db.models.deletion
import modelcluster.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("manuscript", "0005_front_counts"),
    ]

    operations = [
        migrations.CreateModel(
            name="ManuscriptFigureFile",
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
                    "number",
                    models.PositiveIntegerField(verbose_name="Figure number"),
                ),
                (
                    "href",
                    models.CharField(max_length=64, verbose_name="Href"),
                ),
                (
                    "original_name",
                    models.CharField(max_length=255, verbose_name="Original name"),
                ),
                (
                    "file",
                    models.FileField(
                        upload_to="manuscript/figures/%Y/%m/",
                        verbose_name="File",
                    ),
                ),
                (
                    "manuscript",
                    modelcluster.fields.ParentalKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="figure_files",
                        to="manuscript.manuscript",
                    ),
                ),
            ],
            options={
                "verbose_name": "Manuscript figure file",
                "verbose_name_plural": "Manuscript figure files",
                "ordering": ["number"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("manuscript", "number"),
                        name="uniq_manuscript_figure_file_number",
                    )
                ],
            },
        ),
    ]

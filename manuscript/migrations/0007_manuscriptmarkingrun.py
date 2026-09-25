import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("manuscript", "0006_manuscriptfigurefile"),
    ]

    operations = [
        migrations.CreateModel(
            name="ManuscriptMarkingRun",
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
                    "part",
                    models.CharField(
                        choices=[
                            ("front", "Front"),
                            ("body", "Body"),
                            ("back", "Back"),
                        ],
                        max_length=16,
                        verbose_name="Part",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("idle", "Idle"),
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("done", "Done"),
                            ("error", "Error"),
                        ],
                        default="idle",
                        max_length=16,
                        verbose_name="Status",
                    ),
                ),
                (
                    "task_id",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="Task id"
                    ),
                ),
                ("error", models.TextField(blank=True, verbose_name="Error")),
                (
                    "started_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Started at"
                    ),
                ),
                (
                    "finished_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Finished at"
                    ),
                ),
                (
                    "manuscript",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="marking_runs",
                        to="manuscript.manuscript",
                        verbose_name="Manuscript",
                    ),
                ),
            ],
            options={
                "verbose_name": "Manuscript marking run",
                "verbose_name_plural": "Manuscript marking runs",
            },
        ),
        migrations.AddConstraint(
            model_name="manuscriptmarkingrun",
            constraint=models.UniqueConstraint(
                fields=("manuscript", "part"),
                name="uniq_manuscript_marking_run_part",
            ),
        ),
    ]

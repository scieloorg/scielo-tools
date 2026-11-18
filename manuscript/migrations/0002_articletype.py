from django.db import migrations, models

from manuscript.sps_article_types import SPS_ARTICLE_TYPES


def populate_article_types(apps, schema_editor):
    ArticleType = apps.get_model("manuscript", "ArticleType")
    for sort_order, (code, name, description) in enumerate(SPS_ARTICLE_TYPES):
        ArticleType.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "sort_order": sort_order,
            },
        )


def remove_seeded_article_types(apps, schema_editor):
    ArticleType = apps.get_model("manuscript", "ArticleType")
    ArticleType.objects.filter(
        code__in=[code for code, _name, _description in SPS_ARTICLE_TYPES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("manuscript", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArticleType",
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
                    models.CharField(max_length=64, unique=True, verbose_name="Code"),
                ),
                ("name", models.CharField(max_length=128, verbose_name="Name")),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="Description"),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(default=0, verbose_name="Sort order"),
                ),
            ],
            options={
                "verbose_name": "Article type",
                "verbose_name_plural": "Article types",
                "ordering": ["sort_order", "code"],
            },
        ),
        migrations.AlterField(
            model_name="manuscript",
            name="article_type",
            field=models.CharField(
                default="research-article",
                help_text="Closed list of SciELO PS 1.10 @article-type values.",
                max_length=64,
                verbose_name="Article type",
            ),
        ),
        migrations.RunPython(populate_article_types, remove_seeded_article_types),
    ]

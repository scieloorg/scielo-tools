import os

import django.db.models.deletion
from django.db import migrations, models

from manuscript.models import create_figure_image


def copy_figure_files_to_images(apps, schema_editor):
    Figure = apps.get_model("manuscript", "ManuscriptFigureFile")
    for figure in Figure.objects.exclude(file=""):
        name = figure.file.name
        if not name or not figure.file.storage.exists(name):
            continue
        basename = os.path.basename(name)
        with figure.file.open("rb") as fh:
            data = fh.read()
        if not data:
            continue
        image = create_figure_image(
            f"{figure.manuscript_id} {figure.href or basename}",
            data,
            basename,
        )
        figure.image_id = image.pk
        figure.save(update_fields=["image_id"])
        figure.file.delete(save=False)


def noop_copy_figure_files(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("manuscript", "0007_manuscriptmarkingrun"),
        ("wagtailimages", "0027_image_description"),
    ]

    operations = [
        migrations.AddField(
            model_name="manuscriptfigurefile",
            name="image",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="wagtailimages.image",
                verbose_name="Image",
            ),
        ),
        migrations.RunPython(copy_figure_files_to_images, noop_copy_figure_files),
        migrations.RemoveField(
            model_name="manuscriptfigurefile",
            name="file",
        ),
    ]

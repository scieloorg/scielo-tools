import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("manuscript", "0009_manuscriptmarkingrun_endpoints"),
        ("wagtaildocs", "0014_alter_document_file_size"),
    ]

    operations = [
        migrations.AddField(
            model_name="manuscript",
            name="generated_pdf",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="manuscript_generated_pdfs",
                to="wagtaildocs.document",
                verbose_name="Generated PDF",
            ),
        ),
        migrations.AddField(
            model_name="manuscript",
            name="generated_html",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="manuscript_generated_htmls",
                to="wagtaildocs.document",
                verbose_name="Generated HTML",
            ),
        ),
        migrations.AlterField(
            model_name="manuscriptmarkingrun",
            name="part",
            field=models.CharField(
                choices=[
                    ("front", "Front"),
                    ("body", "Body"),
                    ("back", "Back"),
                    ("validate", "Validate"),
                    ("pdf", "PDF"),
                    ("html", "HTML"),
                    ("package", "Package"),
                ],
                max_length=16,
                verbose_name="Part",
            ),
        ),
    ]

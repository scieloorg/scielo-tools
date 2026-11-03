import hashlib

from django.db import migrations, models


def assign_source_sha256(apps, schema_editor):
    Manuscript = apps.get_model("manuscript", "Manuscript")
    seen = set()
    manuscripts = (
        Manuscript.objects.exclude(source_document_id=None)
        .select_related("source_document")
        .order_by("-updated", "-pk")
    )
    for manuscript in manuscripts:
        document = manuscript.source_document
        if document is None:
            continue
        file_field = document.file
        if not file_field:
            continue
        try:
            file_field.open("rb")
            payload = file_field.read()
        except (FileNotFoundError, OSError, ValueError):
            continue
        finally:
            try:
                file_field.close()
            except (FileNotFoundError, OSError, ValueError):
                pass
        if not payload:
            continue
        digest = hashlib.sha256(payload).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        manuscript.source_sha256 = digest
        manuscript.save(update_fields=["source_sha256"])


class Migration(migrations.Migration):
    dependencies = [
        ("manuscript", "0010_manuscript_derived_documents_and_parts"),
        ("wagtaildocs", "0014_alter_document_file_size"),
    ]

    operations = [
        migrations.AddField(
            model_name="manuscript",
            name="source_sha256",
            field=models.CharField(
                blank=True,
                max_length=64,
                null=True,
                unique=True,
                verbose_name="Source SHA256",
            ),
        ),
        migrations.RunPython(assign_source_sha256, migrations.RunPython.noop),
    ]

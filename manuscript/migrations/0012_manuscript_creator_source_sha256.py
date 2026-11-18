from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("manuscript", "0011_manuscript_source_sha256"),
    ]

    operations = [
        migrations.AlterField(
            model_name="manuscript",
            name="source_sha256",
            field=models.CharField(
                blank=True,
                max_length=64,
                null=True,
                verbose_name="Source SHA256",
            ),
        ),
        migrations.AddConstraint(
            model_name="manuscript",
            constraint=models.UniqueConstraint(
                fields=("creator", "source_sha256"),
                name="uniq_manuscript_creator_source_sha256",
            ),
        ),
    ]

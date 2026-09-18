import posixpath
import re

from django.db.models.signals import post_delete
from django.dispatch import receiver
from wagtail.documents.models import Document

from manuscript.models import Manuscript, ManuscriptFigureFile
from xml_manager.models import SPSPackageValidation

_UNIQUE_BEFORE_EXT = re.compile(r"_[A-Za-z0-9]{7}(?=\.)")


def _delete_file_and_unreferenced_family(file_field):
    if not file_field or not file_field.name:
        return
    name = file_field.name
    storage = file_field.storage
    directory, basename = posixpath.split(name)
    original = _UNIQUE_BEFORE_EXT.sub("", basename, count=1)
    family = [name]
    if "." in original:
        stem, rest = original.split(".", 1)
        pattern = re.compile(
            rf"^{re.escape(stem)}(_[A-Za-z0-9]{{7}})?\.{re.escape(rest)}$"
        )
        try:
            _dirs, files = storage.listdir(directory)
        except (FileNotFoundError, OSError):
            files = []
        family = []
        for fname in files:
            if pattern.match(fname):
                family.append(posixpath.join(directory, fname) if directory else fname)
        if name not in family:
            family.append(name)
    referenced = set()
    if family:
        referenced.update(
            Document.objects.filter(file__in=family).values_list("file", flat=True)
        )
        referenced.update(
            ManuscriptFigureFile.objects.filter(file__in=family).values_list(
                "file", flat=True
            )
        )
    for family_name in family:
        if family_name and family_name not in referenced:
            storage.delete(family_name)


@receiver(post_delete, sender=ManuscriptFigureFile)
def delete_manuscript_figure_storage(sender, instance, **kwargs):
    _delete_file_and_unreferenced_family(instance.file)


@receiver(post_delete, sender=Document)
def delete_document_storage(sender, instance, **kwargs):
    _delete_file_and_unreferenced_family(instance.file)


@receiver(post_delete, sender=Manuscript)
def delete_manuscript_related(sender, instance, **kwargs):
    documents = []
    if (
        instance.source_document_id
        and not Manuscript.objects.filter(
            source_document_id=instance.source_document_id
        ).exists()
    ):
        source = Document.objects.filter(pk=instance.source_document_id).first()
        if source:
            documents.append(source)
    if (
        instance.sps_package_id
        and not Manuscript.objects.filter(
            sps_package_id=instance.sps_package_id
        ).exists()
    ):
        package = Document.objects.filter(pk=instance.sps_package_id).first()
        if package:
            documents.append(package)
    if (
        instance.validation_id
        and not Manuscript.objects.filter(validation_id=instance.validation_id).exists()
    ):
        validation = SPSPackageValidation.objects.filter(
            pk=instance.validation_id
        ).first()
        if validation:
            for pk in (
                validation.package_document_id,
                validation.validation_document_id,
                validation.exceptions_document_id,
            ):
                if not pk:
                    continue
                extra = Document.objects.filter(pk=pk).first()
                if extra:
                    documents.append(extra)

    seen = {document.pk for document in documents}

    if seen:
        Document.objects.filter(pk__in=seen).delete()

    if (
        instance.validation_id
        and not Manuscript.objects.filter(validation_id=instance.validation_id).exists()
    ):
        SPSPackageValidation.objects.filter(pk=instance.validation_id).delete()

import hashlib
import posixpath
import re

from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from wagtail.documents.models import Document
from wagtail.images import get_image_model

from body.models import Body
from body.utils import body_checksum, normalize_body_text
from front.models import Front
from front.utils import normalize_front_text
from manuscript.models import (
    Manuscript,
    ManuscriptFigureFile,
    ManuscriptMarkingRun,
    ManuscriptMarkingRunStatus,
    ManuscriptReference,
)
from manuscript.services.marking_jobs import (
    ACTIVE_STATUSES,
    advance_marking_queue,
    revoke_task_ids,
)
from reference.models import ElementCitation, Reference
from reference.utils.references import parse_reference_list, stz_norm
from xml_manager.models import SPSPackageValidation

_UNIQUE_BEFORE_EXT = re.compile(r"_[A-Za-z0-9]{7}(?=\.)")


def _normalized_sha256(text, normalize):
    normalized = normalize(text or "")
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _front_cache_checksum(text):
    return _normalized_sha256(text, normalize_front_text)


def _body_cache_checksum(text):
    normalized = normalize_body_text(text or "")
    if not normalized:
        return ""
    return body_checksum(normalized)


def _checksum_still_used(checksum, texts, checksum_for):
    for text in texts:
        if checksum_for(text) == checksum:
            return True
    return False


def _add_citation_checksums(checksums, citations):
    for citation in citations:
        checksum = _normalized_sha256(citation, stz_norm)
        if checksum:
            checksums.add(checksum)


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
        except FileNotFoundError, OSError:
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
    for family_name in family:
        if family_name and family_name not in referenced:
            storage.delete(family_name)


def delete_unused_manuscript_image(image_id):
    if not image_id:
        return
    if ManuscriptFigureFile.objects.filter(image_id=image_id).exists():
        return
    Image = get_image_model()
    image = Image.objects.filter(pk=image_id).first()
    if image is None:
        return
    for rendition in list(image.renditions.all()):
        _delete_file_and_unreferenced_family(rendition.file)
        rendition.delete()
    _delete_file_and_unreferenced_family(image.file)
    image.delete()


@receiver(post_delete, sender=ManuscriptFigureFile)
def delete_manuscript_figure_image(sender, instance, **kwargs):
    delete_unused_manuscript_image(instance.image_id)


@receiver(post_delete, sender=Document)
def delete_document_storage(sender, instance, **kwargs):
    _delete_file_and_unreferenced_family(instance.file)


@receiver(pre_delete, sender=ManuscriptMarkingRun)
def revoke_deleted_marking_run(sender, instance, **kwargs):
    if instance.task_id and instance.status in ACTIVE_STATUSES:
        revoke_task_ids([instance.task_id])


@receiver(pre_delete, sender=Manuscript)
def remember_manuscript_reference_citations(sender, instance, **kwargs):
    instance._reference_citations = list(
        instance.references.values_list("mixed_citation", flat=True)
    )


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
        instance.generated_pdf_id
        and not Manuscript.objects.filter(
            generated_pdf_id=instance.generated_pdf_id
        ).exists()
    ):
        pdf_doc = Document.objects.filter(pk=instance.generated_pdf_id).first()
        if pdf_doc:
            documents.append(pdf_doc)
    if (
        instance.generated_html_id
        and not Manuscript.objects.filter(
            generated_html_id=instance.generated_html_id
        ).exists()
    ):
        html_doc = Document.objects.filter(pk=instance.generated_html_id).first()
        if html_doc:
            documents.append(html_doc)
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

    front_checksum = _front_cache_checksum(instance.front_source_text)
    if front_checksum and not _checksum_still_used(
        front_checksum,
        Manuscript.objects.values_list("front_source_text", flat=True),
        _front_cache_checksum,
    ):
        Front.objects.filter(checksum=front_checksum).delete()

    body_sum = _body_cache_checksum(instance.body_source_text)
    if body_sum and not _checksum_still_used(
        body_sum,
        Manuscript.objects.values_list("body_source_text", flat=True),
        _body_cache_checksum,
    ):
        Body.objects.filter(checksum=body_sum).delete()

    deleted_reference_checksums = set()
    _add_citation_checksums(
        deleted_reference_checksums,
        getattr(instance, "_reference_citations", []) or [],
    )
    _add_citation_checksums(
        deleted_reference_checksums,
        parse_reference_list(instance.references_source_text or ""),
    )
    if deleted_reference_checksums:
        used_reference_checksums = set()
        for source_text in Manuscript.objects.values_list(
            "references_source_text", flat=True
        ):
            _add_citation_checksums(
                used_reference_checksums,
                parse_reference_list(source_text or ""),
            )
        _add_citation_checksums(
            used_reference_checksums,
            ManuscriptReference.objects.values_list("mixed_citation", flat=True),
        )
        unused_reference_checksums = (
            deleted_reference_checksums - used_reference_checksums
        )
        if unused_reference_checksums:
            reference_ids = Reference.objects.filter(
                checksum__in=unused_reference_checksums
            ).values_list("pk", flat=True)
            ElementCitation.objects.filter(reference_id__in=reference_ids).delete()
            Reference.objects.filter(checksum__in=unused_reference_checksums).delete()

    if ManuscriptMarkingRun.objects.filter(
        status=ManuscriptMarkingRunStatus.PENDING,
        task_id="",
    ).exists():
        advance_marking_queue()

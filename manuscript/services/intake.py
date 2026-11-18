import hashlib
from pathlib import Path

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from wagtail.documents.models import Document

from body.exceptions import BodyDocxError
from body.utils import body_from_docx_upload
from front.exceptions import FrontDocxError
from front.utils import front_from_docx_upload
from manuscript.models import (
    Manuscript,
    ManuscriptMarkingRunStatus,
    ManuscriptStatus,
    get_or_create_manuscript_collection,
)
from manuscript.services.marking_jobs import (
    ACTIVE_STATUSES,
    enqueue_manuscript_marking,
    revoke_task_ids,
)
from reference.exceptions import DocxReferencesError
from reference.utils.references import references_from_docx_upload
from xml_manager.models import SPSPackageValidation


class ManuscriptIntakeError(Exception):
    pass


def extract_all_from_docx(uploaded):
    errors = []
    front_text = ""
    body_text = ""
    references_text = ""
    tables = []
    figures = []
    counts = {}

    try:
        front_text, counts = front_from_docx_upload(uploaded)
    except FrontDocxError as exc:
        errors.append(str(exc))

    uploaded.seek(0)
    try:
        body_text, tables, figures = body_from_docx_upload(uploaded)
    except BodyDocxError as exc:
        errors.append(str(exc))

    uploaded.seek(0)
    try:
        references_text = references_from_docx_upload(uploaded)
    except DocxReferencesError as exc:
        errors.append(str(exc))

    if not any([front_text.strip(), body_text.strip(), references_text.strip()]):
        detail = "; ".join(errors) if errors else _("No content extracted from DOCX")
        raise ManuscriptIntakeError(detail)

    return {
        "front_text": front_text,
        "body_text": body_text,
        "references_text": references_text,
        "tables": tables,
        "figures": figures,
        "counts": counts,
        "errors": errors,
    }


def ingest_docx_into_manuscript(manuscript, docx, user=None, sync_metadata=True):
    payload = docx.read()
    digest = hashlib.sha256(payload).hexdigest()
    docx.seek(0)
    extracted = extract_all_from_docx(docx)
    docx.seek(0)

    target = manuscript
    created = False
    with transaction.atomic():
        existing = (
            Manuscript.objects.select_for_update().filter(source_sha256=digest).first()
        )
        if existing is None:
            was_new = target.pk is None
            target.source_sha256 = digest
            try:
                with transaction.atomic():
                    target.save()
            except IntegrityError:
                existing = Manuscript.objects.select_for_update().get(
                    source_sha256=digest
                )
            else:
                created = was_new
        if existing is not None:
            target = existing
            created = False
            if manuscript.title:
                target.title = manuscript.title
            if sync_metadata:
                target.article_type = manuscript.article_type
                target.language = manuscript.language
                target.specific_use = manuscript.specific_use
            if user is not None:
                target.updated_by = user
            previous_source_id = target.source_document_id
            previous_derived_ids = [
                target.sps_package_id,
                target.generated_pdf_id,
                target.generated_html_id,
            ]
            previous_validation_id = target.validation_id
            active_runs = list(target.marking_runs.filter(status__in=ACTIVE_STATUSES))
            revoke_task_ids([run.task_id for run in active_runs])
            if active_runs:
                target.marking_runs.filter(
                    pk__in=[run.pk for run in active_runs]
                ).update(
                    status=ManuscriptMarkingRunStatus.IDLE,
                    task_id="",
                    error="",
                    finished_at=timezone.now(),
                )
            target.front_marked = {}
            target.front_marked_xml = ""
            target.body_marked = {}
            target.body_marked_xml = ""
            target.assembled_xml = ""
            target.front_approved_at = None
            target.body_approved_at = None
            target.back_approved_at = None
            target.sps_package = None
            target.generated_pdf = None
            target.generated_html = None
            target.validation = None
            target.references.all().delete()
            target.save()
            validation_doc_ids = []
            if (
                previous_validation_id
                and not Manuscript.objects.filter(
                    validation_id=previous_validation_id
                ).exists()
            ):
                validation = SPSPackageValidation.objects.filter(
                    pk=previous_validation_id
                ).first()
                if validation is not None:
                    validation_doc_ids = [
                        validation.package_document_id,
                        validation.validation_document_id,
                        validation.exceptions_document_id,
                    ]
                    validation.delete()
            derived_ids = [
                document_id
                for document_id in (*previous_derived_ids, *validation_doc_ids)
                if document_id
            ]
            for document_id in dict.fromkeys(derived_ids):
                if Manuscript.objects.filter(
                    Q(source_document_id=document_id)
                    | Q(sps_package_id=document_id)
                    | Q(generated_pdf_id=document_id)
                    | Q(generated_html_id=document_id)
                ).exists():
                    continue
                Document.objects.filter(pk=document_id).delete()
        else:
            previous_source_id = None

        collection_name = Path(getattr(docx, "name", "") or "").stem.strip()
        if not collection_name:
            collection_name = (target.title or "").strip()
        if not collection_name:
            collection_name = f"manuscript-{target.pk}"
        collection = get_or_create_manuscript_collection(collection_name)
        document = Document(title=docx.name, collection=collection)
        document.file.save(docx.name, docx, save=True)
        target.source_document = document
        target.source_sha256 = digest
        target.front_source_text = extracted.get("front_text") or ""
        target.body_source_text = extracted.get("body_text") or ""
        target.references_source_text = extracted.get("references_text") or ""
        target.body_tables = extracted.get("tables") or []
        target.body_figures = extracted.get("figures") or []
        target.front_counts = extracted.get("counts") or {}
        target.status = ManuscriptStatus.FRONT
        target.save()
        if (
            previous_source_id
            and previous_source_id != target.source_document_id
            and not Manuscript.objects.filter(
                source_document_id=previous_source_id
            ).exists()
        ):
            Document.objects.filter(pk=previous_source_id).delete()

    enqueue_manuscript_marking(target, user=user)
    return target, extracted, created

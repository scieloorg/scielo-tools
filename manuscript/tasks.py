from celery import shared_task
from django.contrib.auth import get_user_model

from manuscript.models import Manuscript, ManuscriptMarkingPart
from manuscript.services.assembly import (
    generate_manuscript_html_document,
    generate_manuscript_pdf_document,
)
from manuscript.services.marking import (
    MarkingError,
    save_body_marked,
    save_front_marked,
    save_references_items,
)
from manuscript.services.marking_jobs import (
    _refresh_package_run_status,
    advance_marking_queue,
    complete_run,
    fail_run,
)
from manuscript.services.validation import run_manuscript_validation
from xml_manager.models import SPSPackageValidationStatus


def _user_from_id(user_id):
    if user_id is None:
        return None
    return get_user_model().objects.filter(pk=user_id).first()


@shared_task
def persist_front_result(result, manuscript_id, user_id=None):
    marked = result.get("data") if isinstance(result, dict) else {}
    if not isinstance(marked, dict):
        marked = {}
    try:
        manuscript = Manuscript.objects.get(pk=manuscript_id)
        save_front_marked(manuscript, marked, user=_user_from_id(user_id))
    except Exception as exc:
        fail_run(manuscript_id, "front", exc)
        advance_marking_queue(manuscript_id, user_id=user_id, trigger_post_marking=True)
        raise
    complete_run(manuscript_id, "front", endpoints="local")
    advance_marking_queue(manuscript_id, user_id=user_id, trigger_post_marking=True)


@shared_task
def persist_body_result(result, manuscript_id, user_id=None):
    marked = result.get("data") if isinstance(result, dict) else {}
    if not isinstance(marked, dict):
        marked = {}
    try:
        manuscript = Manuscript.objects.get(pk=manuscript_id)
        save_body_marked(manuscript, marked, user=_user_from_id(user_id))
    except Exception as exc:
        fail_run(manuscript_id, "body", exc)
        advance_marking_queue(manuscript_id, user_id=user_id, trigger_post_marking=True)
        raise
    complete_run(manuscript_id, "body", endpoints="local")
    advance_marking_queue(manuscript_id, user_id=user_id, trigger_post_marking=True)


@shared_task
def persist_back_result(result, manuscript_id, user_id=None):
    endpoints = ""
    if isinstance(result, dict) and "items" in result:
        items = result.get("items") or []
        endpoints = result.get("endpoints") or ""
    else:
        items = result if isinstance(result, list) else []
    try:
        manuscript = Manuscript.objects.get(pk=manuscript_id)
        save_references_items(manuscript, items, user=_user_from_id(user_id))
    except MarkingError as exc:
        fail_run(manuscript_id, "back", exc)
        advance_marking_queue(manuscript_id, user_id=user_id, trigger_post_marking=True)
        raise
    except Exception as exc:
        fail_run(manuscript_id, "back", exc)
        advance_marking_queue(manuscript_id, user_id=user_id, trigger_post_marking=True)
        raise
    complete_run(manuscript_id, "back", endpoints=endpoints)
    advance_marking_queue(manuscript_id, user_id=user_id, trigger_post_marking=True)


@shared_task(bind=True)
def run_manuscript_validation_task(self, manuscript_id, user_id=None):
    if getattr(self.request, "id", None):
        self.update_state(state="PROGRESS", meta={"percent": 20})
    try:
        manuscript = Manuscript.objects.get(pk=manuscript_id)
        if getattr(self.request, "id", None):
            self.update_state(state="PROGRESS", meta={"percent": 60})
        validation = run_manuscript_validation(
            manuscript,
            user=_user_from_id(user_id),
            allow_fallback_stem=True,
        )
    except Exception as exc:
        fail_run(manuscript_id, ManuscriptMarkingPart.VALIDATE, exc)
        raise
    if validation is not None and validation.status == SPSPackageValidationStatus.ERROR:
        fail_run(
            manuscript_id,
            ManuscriptMarkingPart.VALIDATE,
            validation.error_message or "Validation failed",
        )
        return
    complete_run(manuscript_id, ManuscriptMarkingPart.VALIDATE, endpoints="local")


@shared_task(bind=True)
def generate_manuscript_pdf_task(self, manuscript_id, user_id=None):
    if getattr(self.request, "id", None):
        self.update_state(state="PROGRESS", meta={"percent": 25})
    try:
        manuscript = Manuscript.objects.get(pk=manuscript_id)
        if getattr(self.request, "id", None):
            self.update_state(state="PROGRESS", meta={"percent": 70})
        generate_manuscript_pdf_document(manuscript)
    except Exception as exc:
        fail_run(manuscript_id, ManuscriptMarkingPart.PDF, exc)
        _refresh_package_run_status(manuscript_id)
        raise
    complete_run(manuscript_id, ManuscriptMarkingPart.PDF, endpoints="local")
    _refresh_package_run_status(manuscript_id)


@shared_task(bind=True)
def generate_manuscript_html_task(self, manuscript_id, user_id=None):
    if getattr(self.request, "id", None):
        self.update_state(state="PROGRESS", meta={"percent": 30})
    try:
        manuscript = Manuscript.objects.get(pk=manuscript_id)
        if getattr(self.request, "id", None):
            self.update_state(state="PROGRESS", meta={"percent": 75})
        generate_manuscript_html_document(manuscript)
    except Exception as exc:
        fail_run(manuscript_id, ManuscriptMarkingPart.HTML, exc)
        _refresh_package_run_status(manuscript_id)
        raise
    complete_run(manuscript_id, ManuscriptMarkingPart.HTML, endpoints="local")
    _refresh_package_run_status(manuscript_id)


@shared_task
def fail_marking_run(request, exc=None, traceback=None, manuscript_id=None, part=None):
    error = ""
    if exc is not None:
        error = str(exc)
    elif request is not None:
        error = str(getattr(request, "exception", request))
    if manuscript_id is None or part is None:
        return
    fail_run(manuscript_id, part, error)
    if part in (ManuscriptMarkingPart.PDF, ManuscriptMarkingPart.HTML):
        _refresh_package_run_status(manuscript_id)
        return
    if part == ManuscriptMarkingPart.VALIDATE:
        return
    advance_marking_queue(manuscript_id, trigger_post_marking=True)

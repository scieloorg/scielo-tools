from celery import shared_task
from django.contrib.auth import get_user_model

from manuscript.models import Manuscript
from manuscript.services.marking import (
    MarkingError,
    save_body_marked,
    save_front_marked,
    save_references_items,
)
from manuscript.services.marking_jobs import complete_run, fail_run


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
        raise
    complete_run(manuscript_id, "front")


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
        raise
    complete_run(manuscript_id, "body")


@shared_task
def persist_back_result(result, manuscript_id, user_id=None):
    items = result if isinstance(result, list) else []
    try:
        manuscript = Manuscript.objects.get(pk=manuscript_id)
        save_references_items(manuscript, items, user=_user_from_id(user_id))
    except MarkingError as exc:
        fail_run(manuscript_id, "back", exc)
        raise
    except Exception as exc:
        fail_run(manuscript_id, "back", exc)
        raise
    complete_run(manuscript_id, "back")


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

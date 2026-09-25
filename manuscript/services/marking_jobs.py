from celery.result import AsyncResult
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from manuscript.models import (
    ManuscriptMarkingPart,
    ManuscriptMarkingRun,
    ManuscriptMarkingRunStatus,
)
from manuscript.services.marking import MarkingError
from reference.utils.references import parse_reference_list

ACTIVE_STATUSES = (
    ManuscriptMarkingRunStatus.PENDING,
    ManuscriptMarkingRunStatus.RUNNING,
)
MARKING_PARTS = (
    ManuscriptMarkingPart.FRONT,
    ManuscriptMarkingPart.BODY,
    ManuscriptMarkingPart.BACK,
)


def part_is_active(manuscript, part):
    return manuscript.marking_runs.filter(
        part=part, status__in=ACTIVE_STATUSES
    ).exists()


def prepare_run(manuscript, part):
    now = timezone.now()
    run, _created = ManuscriptMarkingRun.objects.update_or_create(
        manuscript=manuscript,
        part=part,
        defaults={
            "status": ManuscriptMarkingRunStatus.PENDING,
            "task_id": "",
            "error": "",
            "started_at": now,
            "finished_at": None,
        },
    )
    return run


def complete_run(manuscript_id, part):
    ManuscriptMarkingRun.objects.filter(manuscript_id=manuscript_id, part=part).update(
        status=ManuscriptMarkingRunStatus.DONE,
        error="",
        finished_at=timezone.now(),
    )


def fail_run(manuscript_id, part, error):
    ManuscriptMarkingRun.objects.filter(manuscript_id=manuscript_id, part=part).update(
        status=ManuscriptMarkingRunStatus.ERROR,
        error=str(error or ""),
        finished_at=timezone.now(),
    )


def enqueue_front(manuscript, user=None, counts=None):
    text = (manuscript.front_source_text or "").strip()
    if not text:
        raise MarkingError(_("Front source text is empty"))
    if part_is_active(manuscript, ManuscriptMarkingPart.FRONT):
        raise MarkingError(_("Front marking is already running"))
    from front.tasks import mark_front_text
    from manuscript.tasks import fail_marking_run, persist_front_result

    run = prepare_run(manuscript, ManuscriptMarkingPart.FRONT)
    user_id = user.pk if user is not None else None
    try:
        async_result = mark_front_text.apply_async(
            kwargs={
                "text": text,
                "language": manuscript.language or None,
                "counts": counts or manuscript.front_counts or None,
                "user_id": user_id,
            },
            link=persist_front_result.s(manuscript.pk, user_id),
            link_error=fail_marking_run.s(
                manuscript_id=manuscript.pk,
                part=ManuscriptMarkingPart.FRONT,
            ),
        )
    except Exception as exc:
        fail_run(manuscript.pk, ManuscriptMarkingPart.FRONT, exc)
        raise MarkingError(str(exc)) from exc
    run.task_id = async_result.id or ""
    run.save(update_fields=["task_id"])
    return run


def enqueue_body(manuscript, user=None):
    text = (manuscript.body_source_text or "").strip()
    if not text:
        raise MarkingError(_("Body source text is empty"))
    if part_is_active(manuscript, ManuscriptMarkingPart.BODY):
        raise MarkingError(_("Body marking is already running"))
    from body.tasks import mark_body_text
    from manuscript.tasks import fail_marking_run, persist_body_result

    run = prepare_run(manuscript, ManuscriptMarkingPart.BODY)
    user_id = user.pk if user is not None else None
    image_hrefs = {
        str(item.number): item.href for item in manuscript.figure_files.all()
    }
    try:
        async_result = mark_body_text.apply_async(
            kwargs={
                "text": text,
                "language": manuscript.language or None,
                "tables": manuscript.body_tables or None,
                "figures": manuscript.body_figures or None,
                "image_hrefs": image_hrefs or None,
                "user_id": user_id,
            },
            link=persist_body_result.s(manuscript.pk, user_id),
            link_error=fail_marking_run.s(
                manuscript_id=manuscript.pk,
                part=ManuscriptMarkingPart.BODY,
            ),
        )
    except Exception as exc:
        fail_run(manuscript.pk, ManuscriptMarkingPart.BODY, exc)
        raise MarkingError(str(exc)) from exc
    run.task_id = async_result.id or ""
    run.save(update_fields=["task_id"])
    return run


def enqueue_back(manuscript, user=None):
    text = (manuscript.references_source_text or "").strip()
    if not text:
        raise MarkingError(_("References source text is empty"))
    citations = parse_reference_list(text)
    if not citations:
        raise MarkingError(_("No references found in source text"))
    if part_is_active(manuscript, ManuscriptMarkingPart.BACK):
        raise MarkingError(_("References marking is already running"))
    from manuscript.tasks import fail_marking_run, persist_back_result
    from reference.tasks import mark_reference_texts_task

    run = prepare_run(manuscript, ManuscriptMarkingPart.BACK)
    user_id = user.pk if user is not None else None
    try:
        async_result = mark_reference_texts_task.apply_async(
            kwargs={
                "texts": citations,
                "user_id": user_id,
            },
            link=persist_back_result.s(manuscript.pk, user_id),
            link_error=fail_marking_run.s(
                manuscript_id=manuscript.pk,
                part=ManuscriptMarkingPart.BACK,
            ),
        )
    except Exception as exc:
        fail_run(manuscript.pk, ManuscriptMarkingPart.BACK, exc)
        raise MarkingError(str(exc)) from exc
    run.task_id = async_result.id or ""
    run.save(update_fields=["task_id"])
    return run


def _part_payload(run):
    if run is None:
        return {
            "status": ManuscriptMarkingRunStatus.IDLE,
            "percent": None,
            "error": None,
        }
    payload = {
        "status": run.status,
        "percent": None,
        "error": run.error or None,
    }
    if run.status in ACTIVE_STATUSES:
        payload["percent"] = 0
        if run.task_id:
            result = AsyncResult(run.task_id)
            if result.state in ("STARTED", "PROGRESS"):
                payload["status"] = ManuscriptMarkingRunStatus.RUNNING
            if result.state == "PROGRESS" and isinstance(result.info, dict):
                if result.info.get("percent") is not None:
                    payload["percent"] = result.info.get("percent")
                if result.info.get("done") is not None:
                    payload["done"] = result.info.get("done")
                if result.info.get("total") is not None:
                    payload["total"] = result.info.get("total")
    return payload


def marking_status_payload(manuscript):
    runs = {run.part: run for run in manuscript.marking_runs.all()}
    return {part: _part_payload(runs.get(part)) for part in MARKING_PARTS}

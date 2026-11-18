import logging
from datetime import timedelta

from celery.result import AsyncResult
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from manuscript.models import (
    Manuscript,
    ManuscriptMarkingPart,
    ManuscriptMarkingRun,
    ManuscriptMarkingRunStatus,
    ManuscriptStatus,
)
from manuscript.services.marking import MarkingError
from reference.utils.references import parse_reference_list

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = (
    ManuscriptMarkingRunStatus.PENDING,
    ManuscriptMarkingRunStatus.RUNNING,
)
STALE_RUN_TIMEOUT = timedelta(minutes=32)
MARKING_PARTS = (
    ManuscriptMarkingPart.FRONT,
    ManuscriptMarkingPart.BODY,
    ManuscriptMarkingPart.BACK,
    ManuscriptMarkingPart.VALIDATE,
    ManuscriptMarkingPart.PDF,
    ManuscriptMarkingPart.HTML,
    ManuscriptMarkingPart.PACKAGE,
)
QUEUE_ORDER = (
    ManuscriptMarkingPart.BACK,
    ManuscriptMarkingPart.FRONT,
    ManuscriptMarkingPart.BODY,
)
POST_MARKING_PARTS = (
    ManuscriptMarkingPart.VALIDATE,
    ManuscriptMarkingPart.PDF,
    ManuscriptMarkingPart.HTML,
)
PACKAGE_PROGRESS_PARTS = (
    ManuscriptMarkingPart.FRONT,
    ManuscriptMarkingPart.BODY,
    ManuscriptMarkingPart.BACK,
    ManuscriptMarkingPart.VALIDATE,
    ManuscriptMarkingPart.PACKAGE,
)


def revoke_task_ids(task_ids):
    ids = [str(task_id).strip() for task_id in task_ids if str(task_id or "").strip()]
    if not ids:
        return
    from config.celery_app import app as celery_app

    for task_id in dict.fromkeys(ids):
        try:
            celery_app.control.revoke(task_id, terminate=True)
        except Exception as exc:
            logger.debug("Could not revoke task %s: %s", task_id, exc)


def reconcile_stale_runs(manuscript_id=None):
    qs = (
        ManuscriptMarkingRun.objects.filter(status__in=ACTIVE_STATUSES)
        .exclude(part=ManuscriptMarkingPart.PACKAGE)
        .exclude(task_id="")
    )
    if manuscript_id is not None:
        qs = qs.filter(manuscript_id=manuscript_id)
    runs = list(qs)
    if not runs:
        return False
    now = timezone.now()
    changed = False
    package_refresh_ids = set()
    for run in runs:
        if run.started_at and now - run.started_at > STALE_RUN_TIMEOUT:
            revoke_task_ids([run.task_id])
            fail_run(run.manuscript_id, run.part, _("Marking task timed out"))
            changed = True
            if run.part in (ManuscriptMarkingPart.PDF, ManuscriptMarkingPart.HTML):
                package_refresh_ids.add(run.manuscript_id)
            continue
        try:
            result = AsyncResult(run.task_id)
            state = result.state
            info = result.info
        except Exception as exc:
            logger.debug("Could not inspect task %s: %s", run.task_id, exc)
            continue
        if state in ("FAILURE", "REVOKED"):
            fail_run(run.manuscript_id, run.part, str(info or state))
            changed = True
            if run.part in (ManuscriptMarkingPart.PDF, ManuscriptMarkingPart.HTML):
                package_refresh_ids.add(run.manuscript_id)
    for ms_id in package_refresh_ids:
        _refresh_package_run_status(ms_id)
    return changed


def part_is_active(manuscript, part):
    reconcile_stale_runs(manuscript.pk)
    return manuscript.marking_runs.filter(
        part=part, status__in=ACTIVE_STATUSES
    ).exists()


def _part_is_dispatched(manuscript, part):
    reconcile_stale_runs(manuscript.pk)
    return (
        manuscript.marking_runs.filter(
            part=part,
            status__in=ACTIVE_STATUSES,
        )
        .exclude(task_id="")
        .exists()
    )


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
            "endpoints": "",
        },
    )
    return run


def complete_run(manuscript_id, part, endpoints=""):
    fields = {
        "status": ManuscriptMarkingRunStatus.DONE,
        "error": "",
        "finished_at": timezone.now(),
    }
    if endpoints:
        fields["endpoints"] = endpoints
    ManuscriptMarkingRun.objects.filter(manuscript_id=manuscript_id, part=part).update(
        **fields
    )


def fail_run(manuscript_id, part, error):
    ManuscriptMarkingRun.objects.filter(manuscript_id=manuscript_id, part=part).update(
        status=ManuscriptMarkingRunStatus.ERROR,
        error=str(error or ""),
        finished_at=timezone.now(),
    )


def enqueue_front(manuscript, user=None, counts=None, allow_queued=False):
    text = (manuscript.front_source_text or "").strip()
    if not text:
        raise MarkingError(_("Front source text is empty"))
    check_fn = _part_is_dispatched if allow_queued else part_is_active
    if check_fn(manuscript, ManuscriptMarkingPart.FRONT):
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


def enqueue_body(manuscript, user=None, allow_queued=False):
    text = (manuscript.body_source_text or "").strip()
    if not text:
        raise MarkingError(_("Body source text is empty"))
    check_fn = _part_is_dispatched if allow_queued else part_is_active
    if check_fn(manuscript, ManuscriptMarkingPart.BODY):
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


def enqueue_back(manuscript, user=None, allow_queued=False):
    text = (manuscript.references_source_text or "").strip()
    if not text:
        raise MarkingError(_("References source text is empty"))
    citations = parse_reference_list(text)
    if not citations:
        raise MarkingError(_("No references found in source text"))
    check_fn = _part_is_dispatched if allow_queued else part_is_active
    if check_fn(manuscript, ManuscriptMarkingPart.BACK):
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


def _refresh_package_run_status(manuscript_id):
    runs = {
        run.part: run
        for run in ManuscriptMarkingRun.objects.filter(
            manuscript_id=manuscript_id,
            part__in=(ManuscriptMarkingPart.PDF, ManuscriptMarkingPart.HTML),
        )
    }
    pdf_run = runs.get(ManuscriptMarkingPart.PDF)
    html_run = runs.get(ManuscriptMarkingPart.HTML)
    if pdf_run is None and html_run is None:
        return
    statuses = [run.status for run in (pdf_run, html_run) if run is not None]
    if any(status in ACTIVE_STATUSES for status in statuses):
        return
    if any(status == ManuscriptMarkingRunStatus.ERROR for status in statuses):
        errors = [
            run.error for run in (pdf_run, html_run) if run is not None and run.error
        ]
        fail_run(
            manuscript_id,
            ManuscriptMarkingPart.PACKAGE,
            "; ".join(errors) or "Package generation failed",
        )
        return
    if all(status == ManuscriptMarkingRunStatus.DONE for status in statuses):
        complete_run(manuscript_id, ManuscriptMarkingPart.PACKAGE)


def enqueue_post_marking_tasks(manuscript, user=None):
    from manuscript.services.assembly import refresh_assembled_xml
    from manuscript.tasks import (
        fail_marking_run,
        generate_manuscript_html_task,
        generate_manuscript_pdf_task,
        run_manuscript_validation_task,
    )

    xml = refresh_assembled_xml(manuscript, allow_partial=True)
    if not (xml or manuscript.assembled_xml or "").strip():
        return None
    if (
        manuscript.marking_runs.filter(
            part__in=POST_MARKING_PARTS,
            status__in=ACTIVE_STATUSES,
        )
        .exclude(task_id="")
        .exists()
    ):
        return None
    user_id = user.pk if user is not None else None
    val_run = prepare_run(manuscript, ManuscriptMarkingPart.VALIDATE)
    pdf_run = prepare_run(manuscript, ManuscriptMarkingPart.PDF)
    html_run = prepare_run(manuscript, ManuscriptMarkingPart.HTML)
    pkg_run = prepare_run(manuscript, ManuscriptMarkingPart.PACKAGE)

    dispatched = []
    for run, part, task in (
        (val_run, ManuscriptMarkingPart.VALIDATE, run_manuscript_validation_task),
        (pdf_run, ManuscriptMarkingPart.PDF, generate_manuscript_pdf_task),
        (html_run, ManuscriptMarkingPart.HTML, generate_manuscript_html_task),
    ):
        try:
            async_result = task.apply_async(
                kwargs={
                    "manuscript_id": manuscript.pk,
                    "user_id": user_id,
                },
                link_error=fail_marking_run.s(
                    manuscript_id=manuscript.pk,
                    part=part,
                ),
            )
            run.task_id = async_result.id or ""
            run.save(update_fields=["task_id"])
            dispatched.append(run)
        except Exception as exc:
            fail_run(manuscript.pk, part, exc)
    if pdf_run.task_id or html_run.task_id:
        pkg_run.task_id = pdf_run.task_id or html_run.task_id
        pkg_run.save(update_fields=["task_id"])
    else:
        _refresh_package_run_status(manuscript.pk)
    return dispatched


def advance_marking_queue(manuscript_id=None, user_id=None, trigger_post_marking=False):
    reconcile_stale_runs()
    user = None
    if user_id is not None:
        user = get_user_model().objects.filter(pk=user_id).first()
    manuscript = None
    if manuscript_id is not None:
        manuscript = Manuscript.objects.filter(pk=manuscript_id).first()
        if (
            manuscript is not None
            and trigger_post_marking
            and not manuscript.marking_runs.filter(
                part__in=QUEUE_ORDER,
                status__in=ACTIVE_STATUSES,
            ).exists()
        ):
            enqueue_post_marking_tasks(
                manuscript,
                user=user or manuscript.updated_by or manuscript.creator,
            )
    if (
        ManuscriptMarkingRun.objects.filter(
            part__in=QUEUE_ORDER,
            status__in=ACTIVE_STATUSES,
        )
        .exclude(task_id="")
        .exists()
    ):
        return None
    candidate_ids = []
    if manuscript is not None:
        candidate_ids.append(manuscript.pk)
    waiting_ids = (
        ManuscriptMarkingRun.objects.filter(
            part__in=QUEUE_ORDER,
            status=ManuscriptMarkingRunStatus.PENDING,
            task_id="",
        )
        .order_by("started_at", "manuscript_id", "id")
        .values_list("manuscript_id", flat=True)
    )
    for waiting_id in waiting_ids:
        if waiting_id not in candidate_ids:
            candidate_ids.append(waiting_id)
    for target_id in candidate_ids:
        target = (
            manuscript
            if manuscript is not None and target_id == manuscript.pk
            else Manuscript.objects.filter(pk=target_id).first()
        )
        if target is None:
            continue
        target_user = (
            user
            if (
                manuscript is not None
                and target.pk == manuscript.pk
                and user is not None
            )
            else (target.updated_by or target.creator)
        )
        queued_parts = set(
            target.marking_runs.filter(
                part__in=QUEUE_ORDER,
                status=ManuscriptMarkingRunStatus.PENDING,
                task_id="",
            ).values_list("part", flat=True)
        )
        for part in QUEUE_ORDER:
            if part not in queued_parts:
                continue
            try:
                if part == ManuscriptMarkingPart.BACK:
                    return enqueue_back(target, user=target_user, allow_queued=True)
                if part == ManuscriptMarkingPart.FRONT:
                    return enqueue_front(target, user=target_user, allow_queued=True)
                if part == ManuscriptMarkingPart.BODY:
                    return enqueue_body(target, user=target_user, allow_queued=True)
            except MarkingError as exc:
                fail_run(target.pk, part, exc)
                continue
    return None


def enqueue_manuscript_marking(manuscript, user=None):
    ref_text = (manuscript.references_source_text or "").strip()
    if ref_text and parse_reference_list(ref_text):
        prepare_run(manuscript, ManuscriptMarkingPart.BACK)
    if (manuscript.front_source_text or "").strip():
        prepare_run(manuscript, ManuscriptMarkingPart.FRONT)
    if (manuscript.body_source_text or "").strip():
        prepare_run(manuscript, ManuscriptMarkingPart.BODY)
    user_id = user.pk if user is not None else None
    return advance_marking_queue(manuscript.pk, user_id=user_id)


def _part_payload(run):
    if run is None:
        return {
            "status": ManuscriptMarkingRunStatus.IDLE,
            "percent": None,
            "error": None,
            "endpoints": None,
        }
    payload = {
        "status": run.status,
        "percent": 100 if run.status == ManuscriptMarkingRunStatus.DONE else None,
        "error": run.error or None,
        "endpoints": run.endpoints or None,
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


def _package_payload(runs, manuscript):
    pkg_payload = _part_payload(runs.get(ManuscriptMarkingPart.PACKAGE))
    pdf_payload = _part_payload(runs.get(ManuscriptMarkingPart.PDF))
    html_payload = _part_payload(runs.get(ManuscriptMarkingPart.HTML))
    sub_statuses = [pdf_payload["status"], html_payload["status"]]
    if any(status in ACTIVE_STATUSES for status in sub_statuses):
        pkg_payload["status"] = (
            ManuscriptMarkingRunStatus.RUNNING
            if ManuscriptMarkingRunStatus.RUNNING in sub_statuses
            else ManuscriptMarkingRunStatus.PENDING
        )
        pdf_pct = (
            100
            if pdf_payload["status"] == ManuscriptMarkingRunStatus.DONE
            else (pdf_payload["percent"] or 0)
        )
        html_pct = (
            100
            if html_payload["status"] == ManuscriptMarkingRunStatus.DONE
            else (html_payload["percent"] or 0)
        )
        pkg_payload["percent"] = int((pdf_pct + html_pct) / 2)
    elif all(status == ManuscriptMarkingRunStatus.DONE for status in sub_statuses):
        pkg_payload["status"] = ManuscriptMarkingRunStatus.DONE
        pkg_payload["percent"] = 100
    elif any(status == ManuscriptMarkingRunStatus.ERROR for status in sub_statuses):
        pkg_payload["status"] = ManuscriptMarkingRunStatus.ERROR
        errors = [
            item["error"] for item in (pdf_payload, html_payload) if item.get("error")
        ]
        if errors:
            pkg_payload["error"] = "; ".join(errors)
    elif (
        pkg_payload["status"] == ManuscriptMarkingRunStatus.IDLE
        and manuscript.sps_package_id
    ):
        pkg_payload["status"] = ManuscriptMarkingRunStatus.DONE
        pkg_payload["percent"] = 100
    return pkg_payload


def marking_status_payload(manuscript):
    runs = {run.part: run for run in manuscript.marking_runs.all()}
    if any(run.status in ACTIVE_STATUSES and run.task_id for run in runs.values()):
        if reconcile_stale_runs(manuscript.pk):
            advance_marking_queue(manuscript.pk, trigger_post_marking=True)
            runs = {
                run.part: run
                for run in ManuscriptMarkingRun.objects.filter(manuscript=manuscript)
            }
    payload = {part: _part_payload(runs.get(part)) for part in MARKING_PARTS}
    if (
        payload[ManuscriptMarkingPart.VALIDATE]["status"]
        == ManuscriptMarkingRunStatus.IDLE
        and manuscript.validation_id
    ):
        validation = manuscript.validation
        if validation is not None and validation.status == "done":
            payload[ManuscriptMarkingPart.VALIDATE]["status"] = (
                ManuscriptMarkingRunStatus.DONE
            )
            payload[ManuscriptMarkingPart.VALIDATE]["percent"] = 100
        elif validation is not None and validation.status == "error":
            payload[ManuscriptMarkingPart.VALIDATE]["status"] = (
                ManuscriptMarkingRunStatus.ERROR
            )
            payload[ManuscriptMarkingPart.VALIDATE]["error"] = (
                validation.error_message or None
            )
    payload[ManuscriptMarkingPart.PACKAGE] = _package_payload(runs, manuscript)
    has_front_and_body = bool(
        (
            (manuscript.front_source_text or "").strip()
            or (manuscript.front_marked_xml or "").strip()
        )
        and (
            (manuscript.body_source_text or "").strip()
            or (manuscript.body_marked_xml or "").strip()
        )
    )
    has_references = bool(
        (manuscript.references_source_text or "").strip()
        or ManuscriptMarkingPart.BACK in runs
        or manuscript.back_approved_at
        or manuscript.references.all()
    )
    applicable_parts = [
        part
        for part in PACKAGE_PROGRESS_PARTS
        if part != ManuscriptMarkingPart.BACK
        or has_references
        or not has_front_and_body
    ]
    done_by_status = {
        ManuscriptMarkingPart.FRONT: bool(manuscript.front_approved_at)
        or bool((manuscript.front_marked_xml or "").strip())
        or manuscript.status == ManuscriptStatus.PUBLISHED,
        ManuscriptMarkingPart.BODY: bool(manuscript.body_approved_at)
        or bool((manuscript.body_marked_xml or "").strip())
        or manuscript.status == ManuscriptStatus.PUBLISHED,
        ManuscriptMarkingPart.BACK: bool(manuscript.back_approved_at)
        or any((ref.marked_xml or "").strip() for ref in manuscript.references.all())
        or manuscript.status == ManuscriptStatus.PUBLISHED,
        ManuscriptMarkingPart.VALIDATE: manuscript.status
        in (
            ManuscriptStatus.VALIDATED,
            ManuscriptStatus.READY,
            ManuscriptStatus.PUBLISHED,
        ),
        ManuscriptMarkingPart.PACKAGE: manuscript.status == ManuscriptStatus.PUBLISHED,
    }
    part_percents = []
    part_statuses = []
    for part in applicable_parts:
        info = payload[part]
        status = info["status"]
        part_statuses.append(status)
        if status in ACTIVE_STATUSES:
            pct = info["percent"] or 0
        elif status == ManuscriptMarkingRunStatus.DONE or done_by_status.get(
            part, False
        ):
            pct = 100
        elif info["percent"] is not None:
            pct = info["percent"]
        else:
            pct = 0
        part_percents.append(max(0, min(100, int(pct))))
    overall_percent = (
        int(round(sum(part_percents) / len(part_percents))) if part_percents else 0
    )
    if any(status in ACTIVE_STATUSES for status in part_statuses):
        overall_status = (
            ManuscriptMarkingRunStatus.RUNNING
            if ManuscriptMarkingRunStatus.RUNNING in part_statuses
            else ManuscriptMarkingRunStatus.PENDING
        )
    elif overall_percent == 100:
        overall_status = ManuscriptMarkingRunStatus.DONE
    elif any(status == ManuscriptMarkingRunStatus.ERROR for status in part_statuses):
        overall_status = ManuscriptMarkingRunStatus.ERROR
    else:
        overall_status = ManuscriptMarkingRunStatus.IDLE
    payload["overall"] = {
        "status": overall_status,
        "percent": overall_percent,
    }
    return payload

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from manuscript.models import Manuscript, ManuscriptStatus


class WorkflowError(Exception):
    pass


STEP_ORDER = [
    ManuscriptStatus.DRAFT,
    ManuscriptStatus.FRONT,
    ManuscriptStatus.BODY,
    ManuscriptStatus.BACK,
    ManuscriptStatus.ASSEMBLED,
    ManuscriptStatus.VALIDATED,
    ManuscriptStatus.READY,
    ManuscriptStatus.PUBLISHED,
]

STEP_URLS = {
    ManuscriptStatus.FRONT: "manuscript_step_front",
    ManuscriptStatus.BODY: "manuscript_step_body",
    ManuscriptStatus.BACK: "manuscript_step_back",
    ManuscriptStatus.ASSEMBLED: "manuscript_step_validate",
    ManuscriptStatus.VALIDATED: "manuscript_step_validate",
    ManuscriptStatus.READY: "manuscript_step_package",
}


def current_step_url_name(manuscript):
    if manuscript.status == ManuscriptStatus.DRAFT:
        return "manuscript_step_front"
    return STEP_URLS.get(manuscript.status, "manuscript_step_front")


def open_step(manuscript, step, user=None):
    if step not in STEP_ORDER:
        raise WorkflowError(_("Invalid step: %(step)s") % {"step": step})
    manuscript.status = step
    if step in (
        ManuscriptStatus.FRONT,
        ManuscriptStatus.BODY,
        ManuscriptStatus.BACK,
    ):
        manuscript.validation = None
        if step == ManuscriptStatus.FRONT:
            manuscript.front_approved_at = None
        elif step == ManuscriptStatus.BODY:
            manuscript.body_approved_at = None
        elif step == ManuscriptStatus.BACK:
            manuscript.back_approved_at = None
    if user is not None:
        manuscript.updated_by = user
    manuscript.save()
    return manuscript


def approve_front(manuscript, user=None):
    if manuscript.status not in (ManuscriptStatus.DRAFT, ManuscriptStatus.FRONT):
        raise WorkflowError(_("Cannot approve front from current status"))
    manuscript.status = ManuscriptStatus.BODY
    manuscript.front_approved_at = timezone.now()
    if user is not None:
        manuscript.updated_by = user
    manuscript.save()
    return manuscript


def approve_body(manuscript, user=None):
    if manuscript.status != ManuscriptStatus.BODY:
        raise WorkflowError(_("Cannot approve body from current status"))
    manuscript.status = ManuscriptStatus.BACK
    manuscript.body_approved_at = timezone.now()
    if user is not None:
        manuscript.updated_by = user
    manuscript.save()
    return manuscript


def approve_back(manuscript, user=None):
    if manuscript.status != ManuscriptStatus.BACK:
        raise WorkflowError(_("Cannot approve back from current status"))
    manuscript.status = ManuscriptStatus.ASSEMBLED
    manuscript.back_approved_at = timezone.now()
    if user is not None:
        manuscript.updated_by = user
    manuscript.save()
    return manuscript


def mark_validated(manuscript, user=None):
    if manuscript.status not in (
        ManuscriptStatus.ASSEMBLED,
        ManuscriptStatus.VALIDATED,
    ):
        raise WorkflowError(_("Cannot mark validated from current status"))
    manuscript.status = ManuscriptStatus.VALIDATED
    if user is not None:
        manuscript.updated_by = user
    manuscript.save()
    return manuscript


def mark_ready(manuscript, user=None):
    if manuscript.status != ManuscriptStatus.VALIDATED:
        raise WorkflowError(_("Cannot mark ready from current status"))
    manuscript.status = ManuscriptStatus.READY
    if user is not None:
        manuscript.updated_by = user
    manuscript.save()
    return manuscript

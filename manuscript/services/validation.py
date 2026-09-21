import csv
import io
import json

from django.utils.translation import gettext_lazy as _

from manuscript.models import ManuscriptStatus
from manuscript.services.assembly import build_sps_zip
from manuscript.services.workflow import mark_validated
from xml_manager.models import SPSPackageValidation, SPSPackageValidationStatus
from xml_manager.services import run_sps_package_validation

csv.field_size_limit(10 * 1024 * 1024)


class ValidationError(Exception):
    pass


def parse_validation_csv(document):
    rows, _unreadable = read_validation_csv(document)
    return rows


def read_validation_csv(document):
    if not document:
        return [], False
    try:
        with document.file.open("rb") as fp:
            content = fp.read().decode("utf-8-sig")
    except OSError, ValueError, UnicodeDecodeError:
        return [], True
    reader = csv.DictReader(io.StringIO(content))
    return list(reader), False


def parse_validation_exceptions(document):
    if not document:
        return []
    try:
        with document.file.open("rb") as fp:
            payload = json.load(fp)
    except Exception:
        return []
    if isinstance(payload, list):
        return payload
    return []


VALIDATION_RESPONSE_ORDER = (
    ("CRITICAL", _("Critical")),
    ("ERROR", _("Error")),
    ("WARNING", _("Warning")),
)


def group_validation_rows(rows):
    grouped = {}
    for row in rows:
        group = row.get("group") or "general"
        grouped.setdefault(group, []).append(row)
    return grouped


def response_for_validation_row(row):
    response = (row.get("response") or "").strip().upper()
    known = {key for key, _ in VALIDATION_RESPONSE_ORDER}
    if response in known:
        return response
    if response and response not in ("OK", "EXCEPTION"):
        return "ERROR"
    return None


def group_validation_rows_by_response(rows):
    buckets = {key: [] for key, _ in VALIDATION_RESPONSE_ORDER}
    for row in rows:
        response = response_for_validation_row(row)
        if response:
            buckets[response].append(row)
    return [
        {"response": response, "label": label, "rows": buckets[response]}
        for response, label in VALIDATION_RESPONSE_ORDER
        if buckets[response]
    ]


def run_manuscript_validation(manuscript, user=None):
    build_sps_zip(manuscript)
    package = manuscript.sps_package

    try:
        validation = package.sps_validation
    except SPSPackageValidation.DoesNotExist:
        validation = None

    if validation is None:
        validation = SPSPackageValidation(
            package_document=package,
            status=SPSPackageValidationStatus.PENDING,
            zip_size_bytes=package.file.size,
            validated_by=user,
        )
        validation.save()
    else:
        validation.status = SPSPackageValidationStatus.PENDING
        validation.zip_size_bytes = package.file.size
        validation.validated_by = user
        validation.validated_at = None
        validation.error_message = ""
        validation.save()

    run_sps_package_validation(validation.pk)
    validation.refresh_from_db()
    manuscript.validation = validation
    manuscript.status = ManuscriptStatus.ASSEMBLED
    if user is not None:
        manuscript.updated_by = user
    manuscript.save(update_fields=["validation", "status", "updated", "updated_by"])
    return validation


def confirm_validation_review(manuscript, user=None):
    validation = manuscript.validation
    if validation is None:
        raise ValidationError(_("No validation record"))
    if validation.status != SPSPackageValidationStatus.DONE:
        raise ValidationError(_("Validation is not complete"))
    mark_validated(manuscript, user=user)
    return manuscript


def validation_summary(manuscript):
    validation = manuscript.validation
    if validation is None:
        return {
            "status": None,
            "rows": [],
            "exceptions": [],
            "grouped": {},
            "severities": [],
            "report_unreadable": False,
        }
    rows, report_unreadable = read_validation_csv(validation.validation_document)
    exceptions = parse_validation_exceptions(validation.exceptions_document)
    return {
        "status": validation.status,
        "validated_at": validation.validated_at,
        "error_message": validation.error_message,
        "rows": rows,
        "exceptions": exceptions,
        "grouped": group_validation_rows(rows),
        "severities": group_validation_rows_by_response(rows),
        "validation_document": validation.validation_document,
        "exceptions_document": validation.exceptions_document,
        "report_unreadable": report_unreadable,
    }

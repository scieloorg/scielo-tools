from django.utils.translation import gettext_lazy as _

from body.exceptions import BodyDocxError
from body.utils import body_from_docx_upload
from front.exceptions import FrontDocxError
from front.utils import front_from_docx_upload
from reference.exceptions import DocxReferencesError
from reference.utils.references import references_from_docx_upload


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

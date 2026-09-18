import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.translation import gettext_lazy as _
from lxml import etree

from body.data_utils import get_body_xml, resolve_body_result
from body.exceptions import (
    BodyLlamaDisabledError,
    BodyLlamaMisconfiguredError,
    BodyLlamaUnavailableError,
)
from front.data_utils import get_front_xml, resolve_front_result
from front.exceptions import (
    FrontDocxError,
    FrontLlamaDisabledError,
    FrontLlamaMisconfiguredError,
    FrontLlamaUnavailableError,
)
from front.utils import front_from_docx_upload
from manuscript.models import Manuscript, ManuscriptReference
from reference.data_utils import (
    get_xml,
    resolve_reference_result,
    resolve_references_result,
)
from reference.exceptions import (
    ReferenceLlamaDisabledError,
    ReferenceLlamaMisconfiguredError,
    ReferenceLlamaUnavailableError,
)
from reference.utils.references import parse_reference_list


class MarkingError(Exception):
    pass


LLAMA_ERRORS = (
    FrontLlamaDisabledError,
    FrontLlamaMisconfiguredError,
    FrontLlamaUnavailableError,
    BodyLlamaDisabledError,
    BodyLlamaMisconfiguredError,
    BodyLlamaUnavailableError,
    ReferenceLlamaDisabledError,
    ReferenceLlamaMisconfiguredError,
    ReferenceLlamaUnavailableError,
)


def _sync_assembled_xml(manuscript):
    from manuscript.services.assembly import refresh_assembled_xml

    refresh_assembled_xml(manuscript)


def mark_front(manuscript, user=None, language=None, counts=None):
    text = (manuscript.front_source_text or "").strip()
    if not text:
        raise MarkingError(_("Front source text is empty"))
    if not counts:
        counts = manuscript.front_counts or None
    if not counts:
        document = manuscript.source_document
        if document and document.file:
            try:
                with document.file.open("rb") as fh:
                    uploaded = SimpleUploadedFile(
                        (document.file.name or "source.docx").rsplit("/", 1)[-1],
                        fh.read(),
                        content_type=(
                            "application/vnd.openxmlformats-officedocument."
                            "wordprocessingml.document"
                        ),
                    )
                _front_text, counts = front_from_docx_upload(uploaded)
            except (FrontDocxError, OSError, ValueError):
                counts = None
    try:
        result = resolve_front_result(
            text,
            user=user,
            output_type="json",
            language=language or manuscript.language or None,
            counts=counts,
        )
    except LLAMA_ERRORS as exc:
        raise MarkingError(str(exc)) from exc
    marked = result.get("data") or {}
    manuscript.front_marked = marked
    manuscript.front_marked_xml = get_front_xml(marked)
    update_fields = ["front_marked", "front_marked_xml", "updated", "updated_by"]
    if counts:
        manuscript.front_counts = counts
        update_fields.append("front_counts")
    if user is not None:
        manuscript.updated_by = user
    manuscript.save(update_fields=update_fields)
    _sync_assembled_xml(manuscript)
    return manuscript


def save_front_marked(manuscript, marked, user=None):
    if not isinstance(marked, dict):
        raise MarkingError(_("Front marked data must be a JSON object"))
    manuscript.front_marked = marked
    manuscript.front_marked_xml = get_front_xml(marked)
    if user is not None:
        manuscript.updated_by = user
    manuscript.save(
        update_fields=["front_marked", "front_marked_xml", "updated", "updated_by"]
    )
    _sync_assembled_xml(manuscript)
    return manuscript


def mark_body(manuscript, user=None, language=None):
    text = (manuscript.body_source_text or "").strip()
    if not text:
        raise MarkingError(_("Body source text is empty"))
    image_hrefs = {
        str(item.number): item.href for item in manuscript.figure_files.all()
    }
    try:
        result = resolve_body_result(
            text,
            user=user,
            output_type="json",
            language=language or manuscript.language or None,
            tables=manuscript.body_tables or None,
            figures=manuscript.body_figures or None,
            image_hrefs=image_hrefs or None,
        )
    except LLAMA_ERRORS as exc:
        raise MarkingError(str(exc)) from exc
    marked = result.get("data") or {}
    manuscript.body_marked = marked
    manuscript.body_marked_xml = get_body_xml(marked)
    if user is not None:
        manuscript.updated_by = user
    manuscript.save(
        update_fields=["body_marked", "body_marked_xml", "updated", "updated_by"]
    )
    _sync_assembled_xml(manuscript)
    return manuscript


def save_body_marked(manuscript, marked, user=None):
    if not isinstance(marked, dict):
        raise MarkingError(_("Body marked data must be a JSON object"))
    manuscript.body_marked = marked
    manuscript.body_marked_xml = get_body_xml(marked)
    if user is not None:
        manuscript.updated_by = user
    manuscript.save(
        update_fields=["body_marked", "body_marked_xml", "updated", "updated_by"]
    )
    _sync_assembled_xml(manuscript)
    return manuscript


def build_manuscript_ref_list_xml(manuscript):
    from reference.data_utils import build_ref_list

    results = []
    for ref in manuscript.references.all().order_by("sort_order"):
        results.append(
            {
                "mixed_citation": ref.mixed_citation,
                "data": ref.marked_xml,
            }
        )
    return build_ref_list(results)


def mark_references(manuscript, user=None):
    text = (manuscript.references_source_text or "").strip()
    if not text:
        raise MarkingError(_("References source text is empty"))
    citations = parse_reference_list(text)
    if not citations:
        raise MarkingError(_("No references found in source text"))
    try:
        items = resolve_references_result(citations, user=user, output_type="json")
    except LLAMA_ERRORS as exc:
        raise MarkingError(str(exc)) from exc
    if not items:
        raise MarkingError(_("Could not mark references"))
    manuscript.references.all().delete()
    for sort_order, item in enumerate(items):
        marked = item.get("data") or {}
        marked_xml = ""
        if marked:
            marked_xml = etree.tostring(
                get_xml(json.dumps(marked)),
                pretty_print=True,
                encoding="unicode",
            )
        ManuscriptReference.objects.create(
            manuscript=manuscript,
            mixed_citation=item.get("mixed_citation") or "",
            marked=marked,
            marked_xml=marked_xml,
            sort_order=sort_order,
        )
    if user is not None:
        manuscript.updated_by = user
    manuscript.save(update_fields=["updated", "updated_by"])
    _sync_assembled_xml(manuscript)
    return manuscript


def mark_single_reference(manuscript, reference_pk, user=None):
    ref = ManuscriptReference.objects.get(pk=reference_pk, manuscript=manuscript)
    citation = (ref.mixed_citation or "").strip()
    if not citation:
        raise MarkingError(_("Reference citation is empty"))
    try:
        item = resolve_reference_result(citation, user=user, output_type="json")
    except LLAMA_ERRORS as exc:
        raise MarkingError(str(exc)) from exc
    if item is None:
        raise MarkingError(_("Could not mark reference"))
    marked = item.get("data") or {}
    ref.mixed_citation = item.get("mixed_citation") or citation
    ref.marked = marked
    ref.marked_xml = etree.tostring(
        get_xml(json.dumps(marked)),
        pretty_print=True,
        encoding="unicode",
    )
    ref.save()
    if user is not None:
        manuscript.updated_by = user
        manuscript.save(update_fields=["updated", "updated_by"])
    _sync_assembled_xml(manuscript)
    return ref


def save_references_marked_xml(manuscript, xml_text, user=None):
    try:
        root = etree.fromstring(xml_text.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        raise MarkingError(_("Invalid references XML.")) from exc
    if root.tag != "ref-list":
        raise MarkingError(_("Invalid references XML."))
    manuscript.references.all().delete()
    for index, ref_el in enumerate(root.findall("ref")):
        mixed_el = ref_el.find("mixed-citation")
        mixed = ""
        if mixed_el is not None:
            mixed = "".join(mixed_el.itertext()).strip()
        marked_xml = ""
        for child in ref_el:
            if child.tag == "element-citation":
                marked_xml = etree.tostring(
                    child, pretty_print=True, encoding="unicode"
                )
                break
        ManuscriptReference.objects.create(
            manuscript=manuscript,
            mixed_citation=mixed,
            marked={},
            marked_xml=marked_xml,
            sort_order=index,
        )
    if user is not None:
        manuscript.updated_by = user
    manuscript.save(update_fields=["updated", "updated_by"])
    _sync_assembled_xml(manuscript)
    return manuscript


def save_references_from_payload(manuscript, references_payload, user=None):
    manuscript.references.all().delete()
    for index, item in enumerate(references_payload):
        if not isinstance(item, dict):
            continue
        mixed = item.get("mixed_citation") or ""
        marked = item.get("marked") or {}
        marked_xml = item.get("marked_xml") or ""
        if marked and not marked_xml:
            marked_xml = etree.tostring(
                get_xml(json.dumps(marked)),
                pretty_print=True,
                encoding="unicode",
            )
        ManuscriptReference.objects.create(
            manuscript=manuscript,
            mixed_citation=mixed,
            marked=marked,
            marked_xml=marked_xml,
            sort_order=index,
        )
    if user is not None:
        manuscript.updated_by = user
    manuscript.save(update_fields=["updated", "updated_by"])
    _sync_assembled_xml(manuscript)
    return manuscript

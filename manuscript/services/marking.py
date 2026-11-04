import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.translation import gettext_lazy as _
from lxml import etree

from body.data_utils import get_body_xml, resolve_body_result
from body.exceptions import (
    BodyDocxError,
    BodyLlamaDisabledError,
    BodyLlamaMisconfiguredError,
    BodyLlamaUnavailableError,
)
from body.images import attach_figure_hrefs
from body.utils import body_from_docx_upload
from front.data_utils import apply_text_fields, get_front_xml, resolve_front_result
from front.exceptions import (
    FrontDocxError,
    FrontLlamaDisabledError,
    FrontLlamaMisconfiguredError,
    FrontLlamaUnavailableError,
)
from front.utils import front_from_docx_upload
from manuscript.models import ManuscriptReference
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
    from django.db import transaction

    from manuscript.models import Manuscript
    from manuscript.services.assembly import refresh_assembled_xml

    pk = manuscript.pk
    with transaction.atomic():
        locked = Manuscript.objects.select_for_update().get(pk=pk)
        refresh_assembled_xml(locked)


def _docx_upload(manuscript):
    document = manuscript.source_document
    if document is None or not getattr(document, "file", None):
        return None
    try:
        with document.file.open("rb") as fh:
            payload = fh.read()
    except OSError, ValueError:
        return None
    if not payload:
        return None
    return SimpleUploadedFile(
        (document.file.name or "source.docx").rsplit("/", 1)[-1],
        payload,
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )


def mark_front(manuscript, user=None, language=None, counts=None):
    text = (manuscript.front_source_text or "").strip()
    uploaded = _docx_upload(manuscript)
    if uploaded is not None:
        try:
            fresh_text, fresh_counts = front_from_docx_upload(uploaded)
        except FrontDocxError, OSError, ValueError:
            fresh_text, fresh_counts = "", None
        if fresh_text.strip():
            text = fresh_text.strip()
            if text != (manuscript.front_source_text or "").strip():
                manuscript.front_source_text = text
                manuscript.save(update_fields=["front_source_text", "updated"])
        if not counts and fresh_counts:
            counts = fresh_counts
    if not text:
        raise MarkingError(_("Front source text is empty"))
    if not counts:
        counts = manuscript.front_counts or None
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


def _date_parts_from_element(date):
    return (
        (date.findtext("day") or "").strip(),
        (date.findtext("month") or "").strip(),
        (date.findtext("year") or "").strip(),
    )


def align_publication_history(marked, xml_text=""):
    if not isinstance(marked, dict):
        marked = {}
    raw_history = marked.get("history")
    if not isinstance(raw_history, list) or not raw_history:
        raw_history = marked.get("dates") or []
    history = [dict(item) for item in raw_history if isinstance(item, dict)]
    index_by_type = {}
    for index, item in enumerate(history):
        date_type = str(item.get("type") or item.get("date_type") or "").strip()
        if not date_type:
            continue
        item["type"] = date_type
        index_by_type.setdefault(date_type, index)
    candidates = []
    for item in marked.get("pub_dates") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "pub":
            continue
        candidates.append(
            (
                "pub",
                str(item.get("day") or "").strip(),
                str(item.get("month") or "").strip(),
                str(item.get("year") or "").strip(),
            )
        )
    xml_text = (xml_text or "").strip()
    if xml_text:
        try:
            root = etree.fromstring(xml_text.encode("utf-8"))
        except etree.XMLSyntaxError:
            root = None
        if root is not None:
            for date in root.findall(".//history/date"):
                day, month, year = _date_parts_from_element(date)
                candidates.append(
                    ((date.get("date-type") or "").strip(), day, month, year)
                )
            for date in root.findall(".//pub-date"):
                if (date.get("date-type") or "").strip() != "pub":
                    continue
                day, month, year = _date_parts_from_element(date)
                candidates.append(("pub", day, month, year))
    for date_type, day, month, year in candidates:
        if not date_type or not year:
            continue
        item = {"type": date_type, "year": year}
        if day:
            item["day"] = day
        if month:
            item["month"] = month
        current_index = index_by_type.get(date_type)
        if current_index is None:
            index_by_type[date_type] = len(history)
            history.append(item)
            continue
        current = history[current_index]
        if str(current.get("year") or "").strip():
            continue
        history[current_index] = item
    stored_history = marked.get("history")
    original_history = stored_history if isinstance(stored_history, list) else []
    if history == original_history:
        return marked
    updated = dict(marked)
    if history:
        updated["history"] = history
    elif "history" in updated:
        updated["history"] = history
    published = next(
        (
            item
            for item in history
            if item.get("type") == "pub"
            and str(item.get("day") or "").strip()
            and str(item.get("month") or "").strip()
            and str(item.get("year") or "").strip()
        ),
        None,
    )
    if published is not None:
        pub_dates = [
            dict(entry)
            for entry in (updated.get("pub_dates") or [])
            if isinstance(entry, dict)
        ]
        has_pub = any(
            str(entry.get("type") or "").strip() == "pub" for entry in pub_dates
        )
        if not has_pub:
            pub_dates.append(
                {
                    "type": "pub",
                    "day": published["day"],
                    "month": published["month"],
                    "year": published["year"],
                }
            )
            updated["pub_dates"] = pub_dates
    return updated


def save_front_marked(manuscript, marked, user=None):
    if not isinstance(marked, dict):
        raise MarkingError(_("Front marked data must be a JSON object"))
    marked = align_publication_history(marked)
    manuscript.front_marked = marked
    manuscript.front_marked_xml = get_front_xml(marked)
    if user is not None:
        manuscript.updated_by = user
    manuscript.save(
        update_fields=["front_marked", "front_marked_xml", "updated", "updated_by"]
    )
    _sync_assembled_xml(manuscript)
    return manuscript


def merge_front_history_from_source(manuscript, user=None):
    marked = manuscript.front_marked
    if not isinstance(marked, dict) or not marked:
        return manuscript
    text = (manuscript.front_source_text or "").strip()
    if not text:
        return manuscript
    extracted = apply_text_fields({}, text)
    incoming = [
        item
        for item in (extracted.get("history") or [])
        if isinstance(item, dict)
        and str(item.get("type") or "").strip()
        and str(item.get("year") or "").strip()
    ]
    if not incoming:
        return manuscript
    history = [
        dict(item) for item in (marked.get("history") or []) if isinstance(item, dict)
    ]
    seen = {str(item.get("type") or "").strip() for item in history}
    added = False
    for item in incoming:
        date_type = str(item.get("type") or "").strip()
        if date_type in seen:
            for index, current in enumerate(history):
                if str(current.get("type") or "").strip() != date_type:
                    continue
                if str(current.get("year") or "").strip():
                    break
                history[index] = dict(item)
                added = True
                break
            continue
        history.append(dict(item))
        seen.add(date_type)
        added = True
    marked = dict(marked)
    if history:
        marked["history"] = history
    aligned = align_publication_history(marked, manuscript.front_marked_xml or "")
    if not added and aligned == manuscript.front_marked:
        return manuscript
    marked = aligned
    if "pub" in seen and not any(
        isinstance(item, dict) and str(item.get("type") or "").strip() == "pub"
        for item in (marked.get("pub_dates") or [])
    ):
        pub_dates = [
            dict(item)
            for item in (marked.get("pub_dates") or [])
            if isinstance(item, dict)
        ]
        for item in extracted.get("pub_dates") or []:
            if isinstance(item, dict) and str(item.get("type") or "").strip() == "pub":
                pub_dates.append(dict(item))
                marked["pub_dates"] = pub_dates
                break
    return save_front_marked(manuscript, marked, user=user)


def append_source_references(manuscript, user=None):
    citations = parse_reference_list(manuscript.references_source_text or "")
    if not citations or not manuscript.references.exists():
        return manuscript
    known = {(ref.mixed_citation or "").strip() for ref in manuscript.references.all()}
    last = manuscript.references.order_by("-sort_order").first()
    sort_order = last.sort_order + 1 if last is not None else 0
    created = False
    for citation in citations:
        if citation in known:
            continue
        ManuscriptReference.objects.create(
            manuscript=manuscript,
            mixed_citation=citation,
            marked={},
            marked_xml="",
            sort_order=sort_order,
        )
        known.add(citation)
        sort_order += 1
        created = True
    if not created:
        return manuscript
    if user is not None:
        manuscript.updated_by = user
        manuscript.save(update_fields=["updated", "updated_by"])
    _sync_assembled_xml(manuscript)
    return manuscript


def mark_body(manuscript, user=None, language=None):
    text = (manuscript.body_source_text or "").strip()
    uploaded = _docx_upload(manuscript)
    if uploaded is not None:
        try:
            fresh_text, _tables, _figures = body_from_docx_upload(uploaded)
        except BodyDocxError, OSError, ValueError:
            fresh_text = ""
        if fresh_text.strip():
            text = fresh_text.strip()
            if text != (manuscript.body_source_text or "").strip():
                manuscript.body_source_text = text
                manuscript.save(update_fields=["body_source_text", "updated"])
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
    return save_body_marked(manuscript, result.get("data") or {}, user=user)


def save_body_marked(manuscript, marked, user=None):
    if not isinstance(marked, dict):
        raise MarkingError(_("Body marked data must be a JSON object"))
    image_hrefs = {
        str(item.number): item.href for item in manuscript.figure_files.all()
    }
    if image_hrefs:
        attach_figure_hrefs(marked, image_hrefs)
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
    return save_references_items(manuscript, items, user=user)


def save_references_items(manuscript, items, user=None):
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

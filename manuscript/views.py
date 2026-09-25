import json
import re

from django.contrib import messages
from django.core.exceptions import ValidationError as FormValidationError
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from lxml import etree
from wagtail.admin.auth import require_admin_access

from manuscript.forms import BackStepForm, BodyStepForm, FrontStepForm
from manuscript.i18n import get_manuscript_js_i18n
from manuscript.models import (
    Manuscript,
    ManuscriptFigureFile,
    ManuscriptStatus,
)
from manuscript.preview import (
    ManuscriptPreviewError,
    apply_figure_urls,
    figure_urls_for_manuscript,
    preview_article_xml,
    render_article_preview_packtools,
)
from manuscript.publishers.base import get_publisher, scielo_preview_base_url
from manuscript.services.assembly import (
    AssemblyError,
    assemble_manuscript_xml,
    build_sps_zip,
    refresh_assembled_xml,
)
from manuscript.services.marking import (
    MarkingError,
    build_manuscript_ref_list_xml,
    mark_single_reference,
    save_body_marked,
    save_front_marked,
    save_references_from_payload,
    save_references_marked_xml,
)
from manuscript.services.marking_jobs import (
    enqueue_back,
    enqueue_body,
    enqueue_front,
    marking_status_payload,
)
from manuscript.services.validation import (
    ValidationError,
    confirm_validation_review,
    read_validation_csv,
    response_for_validation_row,
    run_manuscript_validation,
    validation_summary,
)
from manuscript.services.workflow import (
    STEP_ORDER,
    WorkflowError,
    approve_back,
    approve_body,
    approve_front,
    mark_ready,
    open_step,
)
from xml_manager.models import SPSPackageValidationStatus


def _manuscript_or_404(pk):
    return get_object_or_404(Manuscript, pk=pk)


def _wizard_context(request, manuscript, step, form=None):
    status_rank = (
        STEP_ORDER.index(manuscript.status) if manuscript.status in STEP_ORDER else 0
    )
    completed_steps = []
    if status_rank > STEP_ORDER.index(ManuscriptStatus.FRONT):
        completed_steps.append("front")
    if status_rank > STEP_ORDER.index(ManuscriptStatus.BODY):
        completed_steps.append("body")
    if status_rank > STEP_ORDER.index(ManuscriptStatus.BACK):
        completed_steps.append("back")
    if status_rank > STEP_ORDER.index(ManuscriptStatus.ASSEMBLED):
        completed_steps.append("validate")
    if status_rank > STEP_ORDER.index(ManuscriptStatus.READY):
        completed_steps.append("package")
    marking_state = marking_status_payload(manuscript)
    marking_active = {
        part: state.get("status") in ("pending", "running")
        for part, state in marking_state.items()
    }
    validation = manuscript.validation
    validate_has_error = False
    validate_is_complete = "validate" in completed_steps
    if validation is not None:
        if (
            validation.status == SPSPackageValidationStatus.ERROR
            or validation.error_message
        ):
            validate_has_error = True
        else:
            rows, report_unreadable = read_validation_csv(
                validation.validation_document
            )
            if report_unreadable:
                validate_has_error = True
            else:
                validate_has_error = any(
                    response_for_validation_row(row) in ("CRITICAL", "ERROR")
                    for row in rows
                )
            if (
                validation.status == SPSPackageValidationStatus.DONE
                and not validate_has_error
            ):
                validate_is_complete = True
    return {
        "manuscript": manuscript,
        "step": step,
        "form": form,
        "completed_steps": completed_steps,
        "marking_state": marking_state,
        "marking_active": marking_active,
        "validate_has_error": validate_has_error,
        "validate_is_complete": validate_is_complete,
        "preview_base_url": scielo_preview_base_url(),
        "js_i18n": get_manuscript_js_i18n(),
        "header_title": manuscript.title,
        "header_icon": "manuscript",
        "breadcrumbs_items": [
            {"url": reverse("wagtailadmin_home"), "label": _("Home")},
            {
                "url": reverse("wagtailsnippets_manuscript_manuscript:list"),
                "label": _("Manuscripts"),
            },
            {"url": "", "label": manuscript.title},
        ],
    }


@require_admin_access
def step_front(request, pk):
    manuscript = _manuscript_or_404(pk)
    if manuscript.status == ManuscriptStatus.DRAFT:
        open_step(manuscript, ManuscriptStatus.FRONT, user=request.user)

    form = FrontStepForm(
        request.POST or None,
        request.FILES or None,
        initial={"source_text": manuscript.front_source_text},
    )
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action in ("save_source", "mark"):
            source_ready = False
            extracted_counts = None
            if form.is_valid():
                try:
                    text, extracted_counts = form.extract_text()
                except FormValidationError as exc:
                    if (
                        action == "mark"
                        and not form.cleaned_data.get("docx_file")
                        and (manuscript.front_source_text or "").strip()
                    ):
                        text = manuscript.front_source_text
                    else:
                        form.add_error(None, exc)
                        text = None
                if text is not None:
                    manuscript.front_source_text = text
                    update_fields = ["front_source_text", "updated"]
                    if extracted_counts:
                        manuscript.front_counts = extracted_counts
                        update_fields.append("front_counts")
                    manuscript.save(update_fields=update_fields)
                    source_ready = True
            if action == "save_source" and source_ready:
                messages.success(request, _("Front source saved."))
                return redirect("manuscript_step_front", pk=pk)
            if action == "mark" and source_ready:
                try:
                    enqueue_front(
                        manuscript,
                        user=request.user,
                        counts=extracted_counts or manuscript.front_counts,
                    )
                    messages.success(request, _("Front marking started."))
                except MarkingError as exc:
                    messages.error(request, str(exc))
                return redirect("manuscript_step_front", pk=pk)
        if action == "save_marked_xml":
            xml_text = request.POST.get("front_marked_xml", "")
            try:
                etree.fromstring(xml_text.encode("utf-8"))
            except etree.XMLSyntaxError:
                messages.error(request, _("Invalid front XML."))
            else:
                manuscript.front_marked_xml = xml_text
                manuscript.updated_by = request.user
                manuscript.save(
                    update_fields=["front_marked_xml", "updated", "updated_by"]
                )
                refresh_assembled_xml(manuscript)
                messages.success(request, _("Marked text saved."))
            return redirect("manuscript_step_front", pk=pk)
        if action == "approve":
            try:
                approve_front(manuscript, user=request.user)
                messages.success(request, _("Front approved."))
                return redirect("manuscript_step_body", pk=pk)
            except WorkflowError as exc:
                messages.error(request, str(exc))

    context = _wizard_context(request, manuscript, "front", form)
    context["marked_json"] = json.dumps(manuscript.front_marked or {})
    tag_counts = {}
    xml_text = (manuscript.front_marked_xml or "").strip()
    if xml_text:
        try:
            root = etree.fromstring(xml_text.encode("utf-8"))
        except etree.XMLSyntaxError:
            root = None
        if root is not None:
            for node in root.iter():
                tag = etree.QName(node).localname
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    context["front_tag_stats"] = sorted(
        tag_counts.items(), key=lambda item: (-item[1], item[0])
    )
    context["front_tag_stats_total"] = sum(tag_counts.values())
    return render(request, "wagtailadmin/manuscript/step_front.html", context)


@require_admin_access
def step_body(request, pk):
    manuscript = _manuscript_or_404(pk)
    form = BodyStepForm(
        request.POST or None,
        request.FILES or None,
        initial={"source_text": manuscript.body_source_text},
    )
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action in ("save_source", "mark"):
            source_ready = False
            if form.is_valid():
                try:
                    body_text, tables, figures = form.extract_text()
                except FormValidationError as exc:
                    if (
                        action == "mark"
                        and not form.cleaned_data.get("docx_file")
                        and (manuscript.body_source_text or "").strip()
                    ):
                        body_text = manuscript.body_source_text
                        tables, figures = None, None
                    else:
                        form.add_error(None, exc)
                        body_text = None
                if body_text is not None:
                    manuscript.body_source_text = body_text
                    if tables is not None:
                        manuscript.body_tables = tables
                    if figures is not None:
                        manuscript.body_figures = figures
                    manuscript.save(
                        update_fields=[
                            "body_source_text",
                            "body_tables",
                            "body_figures",
                            "updated",
                        ]
                    )
                    for number, asset in (
                        form.cleaned_data.get("image_assets") or {}
                    ).items():
                        figure_number = int(number)
                        href = asset["href"]
                        original_name = asset["original_name"]
                        content = ContentFile(asset["bytes"], name=href)
                        existing = manuscript.figure_files.filter(
                            number=figure_number
                        ).first()
                        if existing:
                            if existing.file:
                                existing.file.delete(save=False)
                            existing.href = href
                            existing.original_name = original_name
                            existing.file.save(href, content, save=True)
                        else:
                            figure = ManuscriptFigureFile(
                                manuscript=manuscript,
                                number=figure_number,
                                href=href,
                                original_name=original_name,
                                sort_order=figure_number,
                            )
                            figure.file.save(href, content, save=True)
                    source_ready = True
            if action == "save_source" and source_ready:
                messages.success(request, _("Body source saved."))
                return redirect("manuscript_step_body", pk=pk)
            if action == "mark" and source_ready:
                try:
                    enqueue_body(manuscript, user=request.user)
                    messages.success(request, _("Body marking started."))
                except MarkingError as exc:
                    messages.error(request, str(exc))
                return redirect("manuscript_step_body", pk=pk)
        if action == "save_marked_xml":
            xml_text = request.POST.get("body_marked_xml", "")
            try:
                etree.fromstring(xml_text.encode("utf-8"))
            except etree.XMLSyntaxError:
                messages.error(request, _("Invalid body XML."))
            else:
                manuscript.body_marked_xml = xml_text
                manuscript.updated_by = request.user
                manuscript.save(
                    update_fields=["body_marked_xml", "updated", "updated_by"]
                )
                refresh_assembled_xml(manuscript)
                messages.success(request, _("Marked text saved."))
            return redirect("manuscript_step_body", pk=pk)
        if action == "approve":
            try:
                approve_body(manuscript, user=request.user)
                messages.success(request, _("Body approved."))
                return redirect("manuscript_step_back", pk=pk)
            except WorkflowError as exc:
                messages.error(request, str(exc))
        if action == "back":
            open_step(manuscript, ManuscriptStatus.FRONT, user=request.user)
            return redirect("manuscript_step_front", pk=pk)

    context = _wizard_context(request, manuscript, "body", form)
    context["marked_json"] = json.dumps(manuscript.body_marked or {})
    return render(request, "wagtailadmin/manuscript/step_body.html", context)


@require_admin_access
def step_back(request, pk):
    manuscript = _manuscript_or_404(pk)
    form = BackStepForm(
        request.POST or None,
        request.FILES or None,
        initial={"source_text": manuscript.references_source_text},
    )
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action in ("save_source", "mark"):
            source_ready = False
            if form.is_valid():
                try:
                    references_text = form.extract_text()
                except FormValidationError as exc:
                    if (
                        action == "mark"
                        and not form.cleaned_data.get("docx_file")
                        and (manuscript.references_source_text or "").strip()
                    ):
                        references_text = manuscript.references_source_text
                    else:
                        form.add_error(None, exc)
                        references_text = None
                if references_text is not None:
                    manuscript.references_source_text = references_text
                    manuscript.save(update_fields=["references_source_text", "updated"])
                    source_ready = True
            if action == "save_source" and source_ready:
                messages.success(request, _("References source saved."))
                return redirect("manuscript_step_back", pk=pk)
            if action == "mark" and source_ready:
                try:
                    enqueue_back(manuscript, user=request.user)
                    messages.success(request, _("References marking started."))
                except MarkingError as exc:
                    messages.error(request, str(exc))
                return redirect("manuscript_step_back", pk=pk)
        if action == "save_marked_xml":
            xml_text = request.POST.get("references_marked_xml", "")
            try:
                save_references_marked_xml(manuscript, xml_text, user=request.user)
            except MarkingError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, _("Marked text saved."))
            return redirect("manuscript_step_back", pk=pk)
        if action == "approve":
            try:
                approve_back(manuscript, user=request.user)
                assemble_manuscript_xml(manuscript)
                messages.success(request, _("Back approved and XML assembled."))
                return redirect("manuscript_step_validate", pk=pk)
            except (WorkflowError, AssemblyError) as exc:
                messages.error(request, str(exc))
        if action == "back":
            open_step(manuscript, ManuscriptStatus.BODY, user=request.user)
            return redirect("manuscript_step_body", pk=pk)

    references = list(manuscript.references.all().order_by("sort_order"))
    references_marked_xml = ""
    if references:
        references_marked_xml = build_manuscript_ref_list_xml(manuscript)
    context = _wizard_context(request, manuscript, "back", form)
    context["references_marked_xml"] = references_marked_xml
    context["references_json"] = json.dumps(
        [
            {
                "id": ref.pk,
                "mixed_citation": ref.mixed_citation,
                "marked": ref.marked,
                "marked_xml": ref.marked_xml,
            }
            for ref in references
        ]
    )
    return render(request, "wagtailadmin/manuscript/step_back.html", context)


@require_admin_access
def step_validate(request, pk):
    manuscript = _manuscript_or_404(pk)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action in ("save_assembled_xml", "validate"):
            if "assembled_xml" in request.POST:
                xml_text = request.POST.get("assembled_xml", "")
                stripped = re.sub(r"<!DOCTYPE[^>]+>", "", xml_text, count=1)
                try:
                    etree.fromstring(stripped.encode("utf-8"))
                except etree.XMLSyntaxError:
                    messages.error(request, _("Invalid assembled XML."))
                    return redirect("manuscript_step_validate", pk=pk)
                manuscript.assembled_xml = xml_text
                manuscript.updated_by = request.user
                manuscript.save(
                    update_fields=["assembled_xml", "updated", "updated_by"]
                )
                if action == "save_assembled_xml":
                    messages.success(request, _("Assembled XML saved."))
                    return redirect("manuscript_step_validate", pk=pk)
        if action == "validate":
            try:
                run_manuscript_validation(manuscript, user=request.user)
                messages.success(request, _("Validation completed."))
            except Exception as exc:
                messages.error(request, str(exc))
            return redirect("manuscript_step_validate", pk=pk)
        if action == "confirm":
            try:
                confirm_validation_review(manuscript, user=request.user)
                mark_ready(manuscript, user=request.user)
                messages.success(request, _("Validation review confirmed."))
                return redirect("manuscript_step_package", pk=pk)
            except (ValidationError, WorkflowError) as exc:
                messages.error(request, str(exc))
            return redirect("manuscript_step_validate", pk=pk)

    summary = validation_summary(manuscript)
    context = _wizard_context(request, manuscript, "validate")
    context["summary"] = summary
    return render(request, "wagtailadmin/manuscript/step_validate.html", context)


@require_admin_access
def step_package(request, pk):
    manuscript = _manuscript_or_404(pk)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "build":
            include_pdf = request.POST.get("include_pdf") == "on"
            try:
                build_sps_zip(manuscript, include_pdf=include_pdf)
                messages.success(request, _("SPS package built."))
            except AssemblyError as exc:
                messages.error(request, str(exc))
            return redirect("manuscript_step_package", pk=pk)
    context = _wizard_context(request, manuscript, "package")
    context["publisher_enabled"] = bool(scielo_preview_base_url())
    return render(request, "wagtailadmin/manuscript/step_package.html", context)


@require_admin_access
@require_GET
@xframe_options_sameorigin
def preview_part(request, pk, part):
    manuscript = _manuscript_or_404(pk)
    if part not in ("front", "body", "back", "article"):
        return HttpResponse(status=404)
    figure_urls = figure_urls_for_manuscript(manuscript)
    try:
        article_xml = preview_article_xml(manuscript, part)
        html_content = apply_figure_urls(
            render_article_preview_packtools(
                article_xml,
                language=manuscript.language,
            ),
            figure_urls,
            xml_text=article_xml,
        )
    except ManuscriptPreviewError as exc:
        html_content = format_html(
            "<p class='alert alert-danger'>{}</p>",
            str(exc),
        )
    return render(
        request,
        "manuscript/article_preview_frame.html",
        {
            "manuscript": manuscript,
            "preview_html": html_content,
            "part": part,
        },
    )


@require_admin_access
@require_http_methods(["POST"])
def api_save_front(request, pk):
    manuscript = _manuscript_or_404(pk)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": _("Invalid JSON")}, status=400)
    marked = payload.get("marked")
    try:
        save_front_marked(manuscript, marked, user=request.user)
    except MarkingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(
        {
            "marked": manuscript.front_marked,
            "marked_xml": manuscript.front_marked_xml,
            "preview_url": reverse("manuscript_preview_part", args=[pk, "front"]),
        }
    )


@require_admin_access
@require_http_methods(["POST"])
def api_save_body(request, pk):
    manuscript = _manuscript_or_404(pk)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": _("Invalid JSON")}, status=400)
    marked = payload.get("marked")
    try:
        save_body_marked(manuscript, marked, user=request.user)
    except MarkingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(
        {
            "marked": manuscript.body_marked,
            "marked_xml": manuscript.body_marked_xml,
            "preview_url": reverse("manuscript_preview_part", args=[pk, "body"]),
        }
    )


@require_admin_access
@require_http_methods(["POST"])
def api_save_back(request, pk):
    manuscript = _manuscript_or_404(pk)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": _("Invalid JSON")}, status=400)
    references = payload.get("references") or []
    try:
        save_references_from_payload(manuscript, references, user=request.user)
    except MarkingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    refs = list(manuscript.references.all().order_by("sort_order"))
    return JsonResponse(
        {
            "references": [
                {
                    "id": ref.pk,
                    "mixed_citation": ref.mixed_citation,
                    "marked": ref.marked,
                    "marked_xml": ref.marked_xml,
                }
                for ref in refs
            ],
            "preview_url": reverse("manuscript_preview_part", args=[pk, "back"]),
        }
    )


@require_admin_access
@require_GET
def api_marking_status(request, pk):
    manuscript = _manuscript_or_404(pk)
    return JsonResponse(marking_status_payload(manuscript))


@require_admin_access
@require_POST
def api_remark_reference(request, pk, ref_pk):
    manuscript = _manuscript_or_404(pk)
    try:
        ref = mark_single_reference(manuscript, ref_pk, user=request.user)
    except MarkingError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(
        {
            "id": ref.pk,
            "mixed_citation": ref.mixed_citation,
            "marked": ref.marked,
            "marked_xml": ref.marked_xml,
        }
    )


@require_admin_access
@require_POST
def api_publish(request, pk):
    manuscript = _manuscript_or_404(pk)
    publisher = get_publisher()
    try:
        publication = publisher.publish(manuscript)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(
        {
            "status": publication.status,
            "preview_url": publication.preview_url,
            "external_id": publication.external_id,
        }
    )

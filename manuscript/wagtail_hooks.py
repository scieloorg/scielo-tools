from django.contrib import messages
from django.http import HttpResponseRedirect
from django.templatetags.static import static
from django.urls import include, path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.navigation import get_site_for_user
from wagtail.admin.site_summary import SummaryItem
from wagtail.admin.ui.tables import Column
from wagtail.admin.widgets.button import Button, HeaderButton
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import CreateView, IndexView, SnippetViewSet

from config.menu import get_menu_order
from manuscript.forms import ManuscriptAdminForm, ManuscriptCreateForm
from manuscript.models import (
    ArticleType,
    Manuscript,
    ManuscriptStatus,
    OriginalLanguage,
)
from manuscript.services.intake import (
    ManuscriptIntakeError,
    ingest_docx_into_manuscript,
)
from manuscript.services.marking_jobs import marking_status_payload
from manuscript.services.workflow import current_step_url_name


class ManuscriptCreateView(CreateView):
    template_name = "wagtailadmin/manuscript/create.html"

    def get_form_class(self):
        return ManuscriptCreateForm

    def get_bound_panel(self, form):
        return None

    def form_valid(self, form):
        manuscript = form.save(commit=False)
        manuscript.creator = self.request.user
        manuscript.updated_by = self.request.user
        manuscript.status = ManuscriptStatus.DRAFT
        docx = form.cleaned_data.get("source_docx")
        created = True
        if docx:
            try:
                manuscript, extracted, created = ingest_docx_into_manuscript(
                    manuscript, docx, user=self.request.user
                )
            except ManuscriptIntakeError as exc:
                messages.error(self.request, str(exc))
                return self.form_invalid(form)
            for warning in extracted.get("errors") or []:
                messages.warning(self.request, warning)
        else:
            manuscript.save()

        if created:
            messages.success(
                self.request,
                _("Manuscript “%(title)s” created.") % {"title": manuscript.title},
            )
        else:
            messages.success(
                self.request,
                _("Manuscript “%(title)s” re-marked.") % {"title": manuscript.title},
            )
        return HttpResponseRedirect(
            reverse("manuscript_step_front", args=[manuscript.pk])
        )


class ManuscriptIndexView(IndexView):
    def get_base_queryset(self):
        return (
            super()
            .get_base_queryset()
            .select_related("source_document", "validation", "sps_package")
            .prefetch_related("marking_runs", "references")
        )

    def get_header_buttons(self):
        buttons = list(super().get_header_buttons())
        if self.permission_policy.user_has_permission(self.request.user, "add"):
            buttons.append(
                HeaderButton(
                    _("Bulk upload"),
                    url=reverse("manuscript_bulk_upload"),
                    icon_name="upload",
                    priority=20,
                )
            )
        return buttons


class ManuscriptWorkflowColumn(Column):
    def get_value(self, instance):
        url_name = current_step_url_name(instance)
        url = reverse(url_name, args=[instance.pk])
        label = instance.get_status_display()
        return format_html('<a href="{}">{}</a>', url, label)


class ManuscriptProgressColumn(Column):
    def get_value(self, instance):
        overall = marking_status_payload(instance)["overall"]
        percent = overall["percent"]
        status = overall["status"]
        active = status in ("pending", "running")
        status_class = ""
        if active:
            status_class = " is-running"
        elif status == "error":
            status_class = " is-error"
        elif status == "done" or percent == 100:
            status_class = " is-complete"
        status_url = reverse("manuscript_api_marking_status", args=[instance.pk])
        return format_html(
            '<div class="manuscript-list-progress{}" '
            'data-manuscript-list-progress="{}" '
            'data-marking-status-url="{}" '
            'data-marking-active="{}">'
            '<span class="manuscript-list-progress__bar" role="progressbar" '
            'aria-valuemin="0" aria-valuemax="100" aria-valuenow="{}">'
            '<span class="manuscript-list-progress__fill" style="width: {}%"></span>'
            "</span>"
            '<span class="manuscript-list-progress__percent">{}%</span>'
            "</div>",
            status_class,
            instance.pk,
            status_url,
            "true" if active else "false",
            percent,
            percent,
            percent,
        )


class ManuscriptSourceDocumentColumn(Column):
    def get_value(self, instance):
        doc = super().get_value(instance)
        if not doc:
            return "-"
        try:
            url = doc.url
        except Exception:
            url = doc.file.url
        return format_html('<a href="{}" target="_blank">{}</a>', url, doc.title)


class CatalogCodeColumn(Column):
    def __init__(self, name, catalog_model, **kwargs):
        super().__init__(name, **kwargs)
        self.catalog_model = catalog_model

    def get_value(self, instance):
        code = (super().get_value(instance) or "").strip()
        if not code:
            return "-"
        match = self.catalog_model.objects.filter(code=code).first()
        if match:
            return str(match)
        return code


class ArticleTypeViewSet(SnippetViewSet):
    model = ArticleType
    icon = "list-ul"
    menu_label = _("Article types")
    list_display = ("code", "name", "sort_order")
    search_fields = ("code", "name")
    ordering = ("sort_order", "code")
    add_to_admin_menu = False
    copy_view_enabled = False


register_snippet(ArticleTypeViewSet)


class OriginalLanguageViewSet(SnippetViewSet):
    model = OriginalLanguage
    icon = "list-ul"
    menu_label = _("Original languages")
    list_display = ("code", "name", "sort_order")
    search_fields = ("code", "name")
    ordering = ("sort_order", "code")
    add_to_admin_menu = False
    copy_view_enabled = False


register_snippet(OriginalLanguageViewSet)


class ManuscriptViewSet(SnippetViewSet):
    model = Manuscript
    index_view_class = ManuscriptIndexView
    add_view_class = ManuscriptCreateView
    icon = "manuscript"
    menu_name = "manuscript"
    menu_label = _("Manuscripts")
    menu_icon = "manuscript"
    menu_order = get_menu_order("manuscript")
    add_to_admin_menu = True
    list_display = (
        "title",
        ManuscriptWorkflowColumn("status", label=_("Status")),
        ManuscriptProgressColumn("progress", label=_("Progress")),
        ManuscriptSourceDocumentColumn("source_document", label=_("Source DOCX")),
        CatalogCodeColumn("article_type", ArticleType, label=_("Article type")),
        CatalogCodeColumn("language", OriginalLanguage, label=_("Original language")),
        "updated",
    )
    list_filter = ("status",)
    search_fields = ("title",)
    copy_view_enabled = False


register_snippet(ManuscriptViewSet)

Manuscript.base_form_class = ManuscriptAdminForm


class ManuscriptsSummaryItem(SummaryItem):
    order = 100
    template_name = "manuscript/home/site_summary_manuscripts.html"

    def get_context_data(self, parent_context):
        site_name = get_site_for_user(self.request.user)["site_name"]
        return {
            "total_manuscripts": Manuscript.objects.count(),
            "site_name": site_name,
        }

    def is_shown(self):
        return self.request.user.has_perm(
            "manuscript.view_manuscript"
        ) or self.request.user.has_perm("manuscript.change_manuscript")


@hooks.register("construct_homepage_summary_items")
def add_manuscripts_summary_item(request, items):
    items.append(ManuscriptsSummaryItem(request))


@hooks.register("register_icons")
def register_manuscript_icons(icons):
    return icons + ["wagtailadmin/icons/manuscript.svg"]


@hooks.register("insert_global_admin_css")
def manuscript_admin_css():
    return format_html(
        '<link rel="stylesheet" href="{}">',
        static("manuscript/css/wizard.css"),
    )


@hooks.register("insert_global_admin_js")
def manuscript_admin_js():
    return format_html(
        '<script src="{}" defer></script>',
        static("manuscript/js/wizard.js"),
    )


@hooks.register("register_admin_urls")
def register_manuscript_admin_urls():
    return [
        path("manuscript/", include("manuscript.urls")),
    ]


@hooks.register("register_snippet_listing_buttons")
def manuscript_listing_buttons(snippet, user, next_url=None):
    if not isinstance(snippet, Manuscript):
        return
    url_name = current_step_url_name(snippet)
    yield Button(
        _("Continue marking"),
        reverse(url_name, args=[snippet.pk]),
        icon_name="manuscript",
        priority=10,
    )

import os

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import include, path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.ui.tables import Column
from wagtail.admin.widgets.button import Button
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import CreateView, EditView, SnippetViewSet

from config.menu import get_menu_order

from . import urls
from .forms import SPSPackageValidationForm
from .models import SPSPackageValidation, SPSPackageValidationStatus
from .services import run_sps_package_validation


class WagtailDocumentLinkColumn(Column):
    def get_value(self, instance):
        doc = super().get_value(instance)
        if not doc:
            return "-"
        try:
            url = doc.url
        except Exception:
            url = doc.file.url
        return format_html('<a href="{}" target="_blank">{}</a>', url, doc.title)


class SPSPackageValidationCreateView(CreateView):
    def get_form_class(self):
        return SPSPackageValidationForm

    def get_bound_panel(self, form):
        return None

    def form_valid(self, form):
        zip_upload = form.cleaned_data["zip_upload"]
        document = SPSPackageValidationForm.save_wagtail_document(zip_upload)
        validation = SPSPackageValidation(
            package_document=document,
            status=SPSPackageValidationStatus.PENDING,
            zip_size_bytes=zip_upload.size,
            validated_by=self.request.user,
        )
        validation.save()
        self.object = validation
        run_sps_package_validation(validation.pk)
        messages.success(
            self.request,
            _("SPS package uploaded. Validation started for “%(title)s”.")
            % {"title": document.title},
        )
        return HttpResponseRedirect(self.get_success_url())


class SPSPackageValidationEditView(EditView):
    def get_form_class(self):
        return SPSPackageValidationForm

    def get_bound_panel(self, form):
        return None

    def form_valid(self, form):
        validation = form.instance
        zip_upload = form.cleaned_data.get("zip_upload")
        if zip_upload:
            if validation.package_document.file:
                validation.package_document.file.delete(save=False)
            validation.package_document.file.save(
                zip_upload.name, zip_upload, save=True
            )
            validation.package_document.save()
            validation.zip_size_bytes = zip_upload.size
            if validation.validation_document:
                validation.validation_document.delete()
                validation.validation_document = None
            if validation.exceptions_document:
                validation.exceptions_document.delete()
                validation.exceptions_document = None
        validation.status = SPSPackageValidationStatus.PENDING
        validation.validated_by = self.request.user
        validation.validated_at = None
        validation.error_message = ""
        validation.save()
        self.object = validation
        run_sps_package_validation(validation.pk)
        messages.success(
            self.request,
            _("Validation started for “%(title)s”.") % {"title": validation},
        )
        return HttpResponseRedirect(self.get_success_url())


class SPSPackageValidationSnippetViewSet(SnippetViewSet):
    model = SPSPackageValidation
    add_view_class = SPSPackageValidationCreateView
    edit_view_class = SPSPackageValidationEditView
    copy_view_enabled = False
    verbose_name = _("SPS package validation")
    verbose_name_plural = _("Validar SPS")
    icon = "sps-package-validation"
    menu_name = "sps_package_validation"
    menu_label = _("Validar SPS")
    menu_icon = "sps-package-validation"
    menu_order = get_menu_order("sps_package_validation")
    add_to_admin_menu = True

    list_display = (
        "__str__",
        WagtailDocumentLinkColumn("package_document", label=_("SPS package (ZIP)")),
        "zip_size_bytes",
        "validated_by",
        "validated_at",
        "status",
        WagtailDocumentLinkColumn("validation_document", label=_("Validation file")),
        WagtailDocumentLinkColumn("exceptions_document", label=_("Exceptions file")),
    )

    list_filter = ("status",)
    search_fields = ("package_document__title",)


register_snippet(SPSPackageValidationSnippetViewSet)


@hooks.register("register_icons")
def register_xml_manager_icons(icons):
    return icons + ["wagtailadmin/icons/sps-package-validation.svg"]


@hooks.register("register_admin_urls")
def register_admin_urls():
    return [
        path("xml-manager/", include(urls)),
    ]


@hooks.register("register_snippet_listing_buttons")
def sps_package_validation_listing_buttons(snippet, user, next_url=None):
    if not isinstance(snippet, SPSPackageValidation):
        return
    yield Button(
        _("Revalidar"),
        reverse("revalidate_sps_package_pk", args=[snippet.pk]),
        icon_name="sps-package-validation",
        priority=25,
    )

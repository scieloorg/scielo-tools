import os

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from wagtail.admin.forms import WagtailAdminModelForm

from xml_manager.models import SPSPackageValidation


class SPSPackageValidationForm(WagtailAdminModelForm):
    zip_upload = forms.FileField(
        label=_("SPS package (.zip)"),
        required=False,
        help_text=_(
            "On edit, leave empty to revalidate the current package without "
            "replacing the file."
        ),
    )

    class Meta:
        model = SPSPackageValidation
        fields = []

    def clean_zip_upload(self):
        zip_upload = self.cleaned_data.get("zip_upload")
        if not zip_upload:
            return zip_upload
        if not zip_upload.name.lower().endswith(".zip"):
            raise ValidationError(_("Only .zip files are allowed."))
        if zip_upload.size == 0:
            raise ValidationError(_("The file is empty."))
        return zip_upload

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk and not cleaned.get("zip_upload"):
            raise ValidationError(_("A .zip file is required."))
        return cleaned

    @staticmethod
    def save_wagtail_document(zip_upload):
        from wagtail.documents.models import Document

        document = Document(title=os.path.basename(zip_upload.name))
        document.file.save(zip_upload.name, zip_upload, save=True)
        return document

    @staticmethod
    def save_wagtail_document_from_path(file_path, title=None):
        return SPSPackageValidationForm.save_or_replace_wagtail_document(
            None, file_path, title=title
        )

    @staticmethod
    def save_or_replace_wagtail_document(document, file_path, title=None):
        from django.core.files import File
        from wagtail.documents.models import Document

        basename = os.path.basename(file_path)
        document_title = title or basename
        with open(file_path, "rb") as fp:
            if document is None:
                document = Document(title=document_title)
            else:
                if document.file:
                    document.file.delete(save=False)
                document.title = document_title
            document.file.save(basename, File(fp), save=True)
        return document

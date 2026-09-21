from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from wagtail.admin.forms import WagtailAdminModelForm

from body.exceptions import BodyDocxError, BodyImageError
from body.images import collect_image_assets
from body.utils import body_from_docx_upload
from front.exceptions import FrontDocxError
from front.utils import front_from_docx_upload
from manuscript.models import ArticleType, Manuscript, OriginalLanguage
from reference.exceptions import DocxReferencesError
from reference.utils.references import references_from_docx_upload


def validate_docx_file(upload):
    if not upload:
        return upload
    name = (getattr(upload, "name", "") or "").lower()
    if not name.endswith(".docx"):
        raise ValidationError(_("Only .docx files are accepted."))
    if getattr(upload, "size", None) == 0:
        raise ValidationError(_("Empty file."))
    return upload


class ManuscriptAdminForm(WagtailAdminModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "article_type" in self.fields:
            article_types = ArticleType.objects.order_by("sort_order", "code")
            self.fields["article_type"] = forms.ChoiceField(
                label=self.fields["article_type"].label,
                help_text=self.fields["article_type"].help_text,
                choices=[(item.code, str(item)) for item in article_types],
                initial=(
                    self.initial.get("article_type")
                    or getattr(self.instance, "article_type", None)
                    or "research-article"
                ),
            )
        if "language" in self.fields:
            languages = OriginalLanguage.objects.order_by("sort_order", "code")
            self.fields["language"] = forms.ChoiceField(
                label=self.fields["language"].label,
                help_text=self.fields["language"].help_text,
                choices=[(item.code, str(item)) for item in languages],
                initial=(
                    self.initial.get("language")
                    or getattr(self.instance, "language", None)
                    or "pt"
                ),
            )


class ManuscriptCreateForm(ManuscriptAdminForm):
    source_docx = forms.FileField(
        label=_("Source DOCX"),
        required=False,
        help_text=_("Optional. Extracts front, body and references sections."),
    )

    class Meta:
        model = Manuscript
        fields = ("title", "article_type", "language", "specific_use")

    def clean_source_docx(self):
        return validate_docx_file(self.cleaned_data.get("source_docx"))

    def save_wagtail_document(self, upload):
        from wagtail.documents.models import Document

        document = Document(title=upload.name)
        document.file.save(upload.name, upload, save=True)
        return document


class StepSourceForm(forms.Form):
    source_text = forms.CharField(
        label=_("Source text"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 12, "class": "form-control"}),
    )
    docx_file = forms.FileField(
        label=_("DOCX file"),
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )

    def clean_docx_file(self):
        return validate_docx_file(self.cleaned_data.get("docx_file"))


class FrontStepForm(StepSourceForm):
    def extract_text(self):
        docx = self.cleaned_data.get("docx_file")
        text = (self.cleaned_data.get("source_text") or "").strip()
        if docx:
            try:
                front_text, counts = front_from_docx_upload(docx)
            except FrontDocxError as exc:
                raise ValidationError(str(exc)) from exc
            return front_text, counts
        if not text:
            raise ValidationError(_("Provide front text or a .docx file."))
        return text, None


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "widget",
            MultipleFileInput(
                attrs={
                    "class": "form-control",
                    "accept": ".tif,.tiff,.jpg,.jpeg,image/tiff,image/jpeg",
                    "multiple": True,
                }
            ),
        )
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data:
            return []
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]
        return [single_file_clean(data, initial)]


class BodyStepForm(StepSourceForm):
    images = MultipleFileField(
        label=_("Package images"),
        required=False,
        help_text=_("fig-N.tif or fig-N.jpg. You can select more than one file."),
    )
    images_zip = forms.FileField(
        label=_("Images zip"),
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": ".zip"}
        ),
        help_text=_("Optional zip with fig-N.tif/jpg files."),
    )

    def clean_images_zip(self):
        upload = self.cleaned_data.get("images_zip")
        if not upload:
            return upload
        name = (getattr(upload, "name", "") or "").lower()
        if not name.endswith(".zip"):
            raise ValidationError(_("Only .zip files are accepted."))
        if getattr(upload, "size", None) == 0:
            raise ValidationError(_("Empty file."))
        return upload

    def clean(self):
        cleaned = super().clean()
        images = cleaned.get("images") or []
        images_zip = cleaned.get("images_zip")
        if not images and not images_zip:
            cleaned["image_assets"] = {}
            return cleaned
        try:
            cleaned["image_assets"] = collect_image_assets(images, images_zip)
        except BodyImageError as exc:
            raise ValidationError(str(exc)) from exc
        return cleaned

    def extract_text(self):
        docx = self.cleaned_data.get("docx_file")
        text = (self.cleaned_data.get("source_text") or "").strip()
        if docx:
            try:
                body_text, tables, figures = body_from_docx_upload(docx)
            except BodyDocxError as exc:
                raise ValidationError(str(exc)) from exc
            return body_text, tables, figures
        if not text:
            raise ValidationError(_("Provide body text or a .docx file."))
        return text, None, None


class BackStepForm(StepSourceForm):
    def extract_text(self):
        docx = self.cleaned_data.get("docx_file")
        text = (self.cleaned_data.get("source_text") or "").strip()
        if docx:
            try:
                references_text = references_from_docx_upload(docx)
            except DocxReferencesError as exc:
                raise ValidationError(str(exc)) from exc
            return references_text
        if not text:
            raise ValidationError(_("Provide references text or a .docx file."))
        return text

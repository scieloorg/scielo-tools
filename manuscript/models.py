from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.panels import FieldPanel
from wagtail.models import Orderable


class ArticleType(models.Model):
    code = models.CharField(_("Code"), max_length=64, unique=True)
    name = models.CharField(_("Name"), max_length=128)
    description = models.TextField(_("Description"), blank=True)
    sort_order = models.PositiveIntegerField(_("Sort order"), default=0)

    panels = [
        FieldPanel("code"),
        FieldPanel("name"),
        FieldPanel("description"),
        FieldPanel("sort_order"),
    ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    class Meta:
        verbose_name = _("Article type")
        verbose_name_plural = _("Article types")
        ordering = ["sort_order", "code"]


class OriginalLanguage(models.Model):
    code = models.CharField(_("Code"), max_length=16, unique=True)
    name = models.CharField(_("Name"), max_length=128)
    sort_order = models.PositiveIntegerField(_("Sort order"), default=0)

    panels = [
        FieldPanel("code"),
        FieldPanel("name"),
        FieldPanel("sort_order"),
    ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    class Meta:
        verbose_name = _("Original language")
        verbose_name_plural = _("Original languages")
        ordering = ["sort_order", "code"]


class ManuscriptStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    FRONT = "front", _("Front")
    BODY = "body", _("Body")
    BACK = "back", _("Back")
    ASSEMBLED = "assembled", _("Assembled")
    VALIDATED = "validated", _("Validated")
    READY = "ready", _("Ready")
    PUBLISHED = "published", _("Published")


class Manuscript(ClusterableModel):
    title = models.CharField(_("Title"), max_length=512)
    status = models.CharField(
        _("Status"),
        max_length=16,
        choices=ManuscriptStatus.choices,
        default=ManuscriptStatus.DRAFT,
    )
    source_document = models.ForeignKey(
        "wagtaildocs.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="manuscripts",
        verbose_name=_("Source DOCX"),
    )
    article_type = models.CharField(
        _("Article type"),
        max_length=64,
        default="research-article",
        help_text=_("Closed list of SciELO PS 1.10 @article-type values."),
    )
    language = models.CharField(
        _("Original language"),
        max_length=16,
        default="pt",
        help_text=_(
            "Closed list of ISO 639-1 codes for the article original language."
        ),
    )
    specific_use = models.CharField(
        _("SPS version"),
        max_length=32,
        default="sps-1.10",
    )
    front_source_text = models.TextField(_("Front source text"), blank=True)
    front_counts = models.JSONField(_("Front counts"), default=dict, blank=True)
    front_marked = models.JSONField(_("Front marked"), default=dict, blank=True)
    front_marked_xml = models.TextField(_("Front marked XML"), blank=True)
    body_source_text = models.TextField(_("Body source text"), blank=True)
    body_marked = models.JSONField(_("Body marked"), default=dict, blank=True)
    body_marked_xml = models.TextField(_("Body marked XML"), blank=True)
    body_tables = models.JSONField(_("Body tables"), default=list, blank=True)
    body_figures = models.JSONField(_("Body figures"), default=list, blank=True)
    references_source_text = models.TextField(_("References source text"), blank=True)
    assembled_xml = models.TextField(_("Assembled XML"), blank=True)
    sps_package = models.ForeignKey(
        "wagtaildocs.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="manuscript_sps_packages",
        verbose_name=_("SPS package"),
    )
    validation = models.ForeignKey(
        "xml_manager.SPSPackageValidation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="manuscripts",
        verbose_name=_("Validation"),
    )
    front_approved_at = models.DateTimeField(
        _("Front approved at"), null=True, blank=True
    )
    body_approved_at = models.DateTimeField(
        _("Body approved at"), null=True, blank=True
    )
    back_approved_at = models.DateTimeField(
        _("Back approved at"), null=True, blank=True
    )
    created = models.DateTimeField(_("Created"), auto_now_add=True)
    updated = models.DateTimeField(_("Updated"), auto_now=True)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Creator"),
        related_name="manuscripts_created",
        editable=False,
        on_delete=models.SET_NULL,
        null=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Updated by"),
        related_name="manuscripts_updated",
        editable=False,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    panels = [
        FieldPanel("title"),
        FieldPanel("status"),
        FieldPanel("source_document"),
        FieldPanel("article_type"),
        FieldPanel("language"),
        FieldPanel("specific_use"),
    ]

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = _("Manuscript")
        verbose_name_plural = _("Manuscripts")
        ordering = ["-updated"]


class ManuscriptFigureFile(Orderable):
    manuscript = ParentalKey(
        Manuscript,
        on_delete=models.CASCADE,
        related_name="figure_files",
    )
    number = models.PositiveIntegerField(_("Figure number"))
    href = models.CharField(_("Href"), max_length=64)
    original_name = models.CharField(_("Original name"), max_length=255)
    file = models.FileField(_("File"), upload_to="manuscript/figures/%Y/%m/")

    panels = [
        FieldPanel("number"),
        FieldPanel("href"),
        FieldPanel("original_name"),
        FieldPanel("file"),
    ]

    def __str__(self):
        return self.href

    class Meta:
        verbose_name = _("Manuscript figure file")
        verbose_name_plural = _("Manuscript figure files")
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(
                fields=["manuscript", "number"],
                name="uniq_manuscript_figure_file_number",
            )
        ]


class ManuscriptReference(Orderable):
    manuscript = ParentalKey(
        Manuscript,
        on_delete=models.CASCADE,
        related_name="references",
    )
    mixed_citation = models.TextField(_("Mixed citation"), blank=True)
    marked = models.JSONField(_("Marked"), default=dict, blank=True)
    marked_xml = models.TextField(_("Marked XML"), blank=True)
    score = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )

    panels = [
        FieldPanel("mixed_citation"),
        FieldPanel("marked"),
        FieldPanel("marked_xml"),
        FieldPanel("score"),
    ]

    class Meta:
        verbose_name = _("Manuscript reference")
        verbose_name_plural = _("Manuscript references")


class ManuscriptPublication(models.Model):
    manuscript = models.ForeignKey(
        Manuscript,
        on_delete=models.CASCADE,
        related_name="publications",
        verbose_name=_("Manuscript"),
    )
    external_id = models.CharField(_("External ID"), max_length=255, blank=True)
    preview_url = models.URLField(_("Preview URL"), blank=True)
    published_at = models.DateTimeField(_("Published at"), null=True, blank=True)
    status = models.CharField(_("Status"), max_length=32, default="pending")

    class Meta:
        verbose_name = _("Manuscript publication")
        verbose_name_plural = _("Manuscript publications")

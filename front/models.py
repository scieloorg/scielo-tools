import hashlib

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from front.utils import normalize_front_text


class Front(models.Model):
    source_text = models.TextField(_("Source text"))
    normalized_text = models.TextField(_("Normalized text"), blank=True, db_index=True)
    checksum = models.CharField(_("SHA256"), max_length=64, blank=True, unique=True)
    marked = models.JSONField(_("Marked"), default=dict, blank=True)
    marked_xml = models.TextField(_("Marked XML"), blank=True)
    created = models.DateTimeField(verbose_name=_("Creation date"), auto_now_add=True)
    updated = models.DateTimeField(verbose_name=_("Last update date"), auto_now=True)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Creator"),
        related_name="%(class)s_creator",
        editable=False,
        on_delete=models.SET_NULL,
        null=True,
    )

    def __str__(self):
        return self.checksum

    def save(self, *args, **kwargs):
        self.normalized_text = normalize_front_text(self.source_text)
        self.checksum = hashlib.sha256(self.normalized_text.encode("utf-8")).hexdigest()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("Front")
        verbose_name_plural = _("Fronts")

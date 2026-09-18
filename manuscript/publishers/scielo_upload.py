from django.utils.translation import gettext_lazy as _

from manuscript.models import ManuscriptPublication
from manuscript.publishers.base import (
    BasePublisher,
    PublishError,
    scielo_preview_base_url,
)


class SciELOUploadPublisher(BasePublisher):
    def publish(self, manuscript):
        if not (manuscript.assembled_xml or "").strip():
            raise PublishError(_("Assembled XML is required before publishing."))
        publication = ManuscriptPublication.objects.create(
            manuscript=manuscript,
            status="pending",
            external_id="",
            preview_url=self.preview_url(manuscript),
        )
        return publication

    def preview_url(self, manuscript):
        base = scielo_preview_base_url()
        if not base:
            return ""
        slug = manuscript.pk
        return f"{base.rstrip('/')}/preview/{slug}"

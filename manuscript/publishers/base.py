from django.conf import settings


class PublishError(Exception):
    pass


class BasePublisher:
    def publish(self, manuscript):
        raise NotImplementedError

    def preview_url(self, manuscript):
        raise NotImplementedError


def get_publisher():
    from manuscript.publishers.scielo_upload import SciELOUploadPublisher

    return SciELOUploadPublisher()


def scielo_preview_base_url():
    return getattr(settings, "SCIELO_PREVIEW_BASE_URL", "")

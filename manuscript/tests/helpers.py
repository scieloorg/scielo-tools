from wagtail.images import get_image_model
from wagtail.images.tests.utils import get_test_image_file

from manuscript.models import ManuscriptFigureFile


def attach_manuscript_figure(manuscript, number=1, href=None, original_name=None):
    href = href or f"fig-{number}.jpg"
    original_name = original_name or href
    image = get_image_model().objects.create(
        title=f"{manuscript.pk} {href}",
        file=get_test_image_file(filename=href),
    )
    figure = ManuscriptFigureFile(
        manuscript=manuscript,
        number=number,
        href=href,
        original_name=original_name,
        sort_order=number,
        image=image,
    )
    figure.save()
    return figure

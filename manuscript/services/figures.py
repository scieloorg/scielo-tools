from pathlib import Path

from django.db import transaction

from body.data_utils import get_body_xml
from body.images import attach_figure_hrefs, normalize_figure_identifier
from manuscript.models import (
    ManuscriptFigureFile,
    create_figure_image,
    get_or_create_manuscript_collection,
)
from manuscript.services.assembly import refresh_assembled_xml
from manuscript.signals import delete_unused_manuscript_image


def sync_manuscript_figure_hrefs(manuscript):
    marked = manuscript.body_marked
    if not isinstance(marked, dict) or not marked:
        return
    image_hrefs = {
        str(item.number): item.href for item in manuscript.figure_files.all()
    }
    attach_figure_hrefs(marked, image_hrefs)
    manuscript.body_marked = marked
    manuscript.body_marked_xml = get_body_xml(marked)
    manuscript.save(update_fields=["body_marked", "body_marked_xml", "updated"])
    refresh_assembled_xml(manuscript)


def save_manuscript_image_assets(manuscript, image_assets, collection_name=""):
    if not image_assets:
        return []
    name = (collection_name or "").strip()
    if not name and manuscript.source_document_id and manuscript.source_document:
        if manuscript.source_document.collection_id:
            name = manuscript.source_document.collection.name
        else:
            name = Path(manuscript.source_document.title or "").stem.strip()
    if not name:
        name = (manuscript.title or "").strip()
    if not name:
        name = f"manuscript-{manuscript.pk}"
    collection = get_or_create_manuscript_collection(name)
    saved_figures = []
    for number, asset in image_assets.items():
        figure_number = int(number)
        href = asset["href"]
        original_name = asset["original_name"]
        image = create_figure_image(
            f"{manuscript.pk} {href}",
            asset["bytes"],
            href,
            collection,
        )
        existing = manuscript.figure_files.filter(number=figure_number).first()
        if existing:
            old_image_id = existing.image_id
            existing.href = href
            existing.original_name = original_name
            existing.image = image
            existing.save()
            if old_image_id:
                delete_unused_manuscript_image(old_image_id)
            saved_figures.append(existing)
        else:
            created = ManuscriptFigureFile.objects.create(
                manuscript=manuscript,
                number=figure_number,
                href=href,
                original_name=original_name,
                sort_order=figure_number,
                image=image,
            )
            saved_figures.append(created)
    sync_manuscript_figure_hrefs(manuscript)
    return saved_figures


def rename_manuscript_figure(manuscript, figure_file, new_identifier):
    target_number, target_href = normalize_figure_identifier(new_identifier)
    with transaction.atomic():
        conflict = (
            manuscript.figure_files.select_for_update()
            .filter(number=target_number)
            .exclude(pk=figure_file.pk)
            .first()
        )
        old_number = figure_file.number
        old_href = f"fig-{old_number}.jpg"
        if conflict is not None:
            temp_number = (
                max(
                    manuscript.figure_files.values_list("number", flat=True),
                    default=target_number,
                )
                + 1000
            )
            conflict.number = temp_number
            conflict.save(update_fields=["number"])
        figure_file.number = target_number
        figure_file.href = target_href
        figure_file.sort_order = target_number
        figure_file.save(update_fields=["number", "href", "sort_order"])
        if figure_file.image_id and figure_file.image:
            figure_file.image.title = f"{manuscript.pk} {target_href}"
            figure_file.image.save(update_fields=["title"])
        if conflict is not None:
            conflict.number = old_number
            conflict.href = old_href
            conflict.sort_order = old_number
            conflict.save(update_fields=["number", "href", "sort_order"])
            if conflict.image_id and conflict.image:
                conflict.image.title = f"{manuscript.pk} {old_href}"
                conflict.image.save(update_fields=["title"])
    sync_manuscript_figure_hrefs(manuscript)
    return figure_file


def delete_manuscript_figure(manuscript, figure_file):
    figure_file.delete()
    sync_manuscript_figure_hrefs(manuscript)

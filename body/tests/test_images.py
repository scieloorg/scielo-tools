import io
import zipfile
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from lxml import etree
from PIL import Image

from body.data_utils import get_body_xml
from body.exceptions import BodyImageError
from body.images import (
    attach_figure_hrefs,
    collect_image_assets,
    collect_image_hrefs,
    parse_figure_filename,
)

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "mr-2025-0610"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def make_tiff_bytes(size=(2, 2), color=(255, 0, 0)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="TIFF")
    return buffer.getvalue()


def make_jpeg_bytes(size=(2, 2), color=(0, 255, 0)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="JPEG")
    return buffer.getvalue()


def uploaded_image(name, content, content_type="image/tiff"):
    return SimpleUploadedFile(name, content, content_type=content_type)


def test_parse_figure_filename_canonical_number():
    assert parse_figure_filename("fig-1.tif") == ("1", "tif")
    assert parse_figure_filename("fig-01.TIFF") == ("1", "tiff")
    assert parse_figure_filename("folder/fig-3.jpg") == ("3", "jpg")
    assert parse_figure_filename("fig-2.jpeg") == ("2", "jpeg")
    assert parse_figure_filename("FIG-8.JPG") == ("8", "jpg")
    assert parse_figure_filename("figure-1.jpg") is None
    assert parse_figure_filename("fig-1.png") is None
    assert parse_figure_filename("readme.txt") is None


def test_collect_image_assets_converts_tiff_to_jpeg_bytes():
    assets = collect_image_assets([uploaded_image("fig-1.tif", make_tiff_bytes())])
    assert set(assets) == {"1"}
    assert assets["1"]["href"] == "fig-1.jpg"
    assert assets["1"]["original_name"] == "fig-1.tif"
    assert assets["1"]["bytes"].startswith(b"\xff\xd8")


def test_collect_image_hrefs_converts_tiff_and_keeps_jpeg_name():
    hrefs = collect_image_hrefs(
        [
            uploaded_image("fig-1.tif", make_tiff_bytes()),
            uploaded_image("fig-3.jpg", make_jpeg_bytes(), content_type="image/jpeg"),
        ]
    )
    assert hrefs == {"1": "fig-1.jpg", "3": "fig-3.jpg"}


def test_collect_image_hrefs_strips_zero_padding():
    hrefs = collect_image_hrefs([uploaded_image("fig-01.tif", make_tiff_bytes())])
    assert hrefs == {"1": "fig-1.jpg"}


def test_collect_image_hrefs_from_mr_fixture():
    tif_path = FIXTURE_DIR / "fig-1.tif"
    jpg_path = FIXTURE_DIR / "fig-3.jpg"
    hrefs = collect_image_hrefs(
        [
            uploaded_image("fig-1.tif", tif_path.read_bytes()),
            uploaded_image(
                "fig-3.jpg", jpg_path.read_bytes(), content_type="image/jpeg"
            ),
        ]
    )
    assert hrefs == {"1": "fig-1.jpg", "3": "fig-3.jpg"}


def test_collect_image_hrefs_from_zip_ignores_other_files():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("fig-1.tif", make_tiff_bytes())
        zipped.writestr("readme.txt", "ignore me")
        zipped.writestr("article.docx", b"not a figure")
    archive.seek(0)
    uploaded = SimpleUploadedFile(
        "figures.zip", archive.getvalue(), content_type="application/zip"
    )
    hrefs = collect_image_hrefs(images_zip=uploaded)
    assert hrefs == {"1": "fig-1.jpg"}


def test_collect_image_hrefs_rejects_invalid_loose_filename():
    with pytest.raises(BodyImageError, match="Invalid image filename"):
        collect_image_hrefs(
            [uploaded_image("photo.png", make_jpeg_bytes(), "image/png")]
        )


def test_collect_image_hrefs_rejects_duplicate_numbers():
    with pytest.raises(BodyImageError, match="Duplicate figure number"):
        collect_image_hrefs(
            [
                uploaded_image("fig-1.tif", make_tiff_bytes()),
                uploaded_image(
                    "fig-1.jpg", make_jpeg_bytes(), content_type="image/jpeg"
                ),
            ]
        )


def test_collect_image_hrefs_rejects_corrupt_tiff():
    with pytest.raises(BodyImageError, match="Could not convert"):
        collect_image_hrefs([uploaded_image("fig-1.tif", b"not a tiff")])


def test_collect_image_hrefs_rejects_bad_zip():
    uploaded = SimpleUploadedFile(
        "figures.zip", b"not-a-zip", content_type="application/zip"
    )
    with pytest.raises(BodyImageError, match="Invalid zip file"):
        collect_image_hrefs(images_zip=uploaded)


def test_attach_figure_hrefs_sets_fig_and_fig_group():
    marked = {
        "sections": [
            {
                "content": [
                    {
                        "type": "fig",
                        "id": "f1",
                        "label": "Figure 1",
                        "caption": "One",
                    },
                    {
                        "type": "fig-group",
                        "figs": [
                            {
                                "type": "fig",
                                "id": "f2",
                                "label": "Figure 2",
                            }
                        ],
                    },
                ],
                "sections": [],
            }
        ]
    }
    attach_figure_hrefs(marked, {"1": "fig-1.jpg", "2": "fig-2.jpg"})
    assert marked["sections"][0]["content"][0]["href"] == "fig-1.jpg"
    assert marked["sections"][0]["content"][1]["figs"][0]["href"] == "fig-2.jpg"


def test_get_body_xml_emits_graphic_href_from_attached_images():
    marked = {
        "sections": [
            {
                "sec_type": "intro",
                "title": "Introduction",
                "content": [
                    {
                        "type": "fig",
                        "id": "f1",
                        "label": "Figure 1",
                        "caption": "Map",
                    }
                ],
                "sections": [],
            }
        ]
    }
    attach_figure_hrefs(marked, {"1": "fig-1.jpg"})
    xml = get_body_xml(marked)
    root = etree.fromstring(xml.encode("utf-8"))
    graphic = root.find(".//graphic")
    assert graphic is not None
    assert graphic.get("id") == "g1"
    assert graphic.get(XLINK_HREF) == "fig-1.jpg"

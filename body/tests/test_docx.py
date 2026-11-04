import io
import json
import zipfile
from xml.sax.saxutils import escape

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from body.utils import (
    NESTED_HEADING_MARK,
    body_from_docx_upload,
    extract_body_section,
    section_from_plain_text,
    split_body_sections,
)


def make_docx_bytes(paragraphs, tables=None, heading_styles=None):
    heading_styles = heading_styles or {}
    parts = []
    for paragraph in paragraphs:
        style_name = heading_styles.get(paragraph)
        style_xml = (
            f'<w:pPr><w:pStyle w:val="{escape(style_name)}"/></w:pPr>'
            if style_name
            else ""
        )
        parts.append(f"<w:p>{style_xml}<w:r><w:t>{escape(paragraph)}</w:t></w:r></w:p>")
    for table in tables or []:
        rows_xml = []
        for row in table:
            cells = "".join(
                f"<w:tc><w:p><w:r><w:t>{escape(str(cell))}</w:t></w:r></w:p></w:tc>"
                for cell in row
            )
            rows_xml.append(f"<w:tr>{cells}</w:tr>")
        parts.append(f"<w:tbl>{''.join(rows_xml)}</w:tbl>")
    body = "".join(parts)
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", ""),
        (
            "Título\nAna Silva\nIntroduction\nBody of the article\n"
            "References\nSmith 2020",
            "Introduction\nBody of the article",
        ),
        (
            "Título\n1. Introdução\nCorpo\nAgradecimentos\nCNPq 1",
            "1. Introdução\nCorpo\nAgradecimentos\nCNPq 1",
        ),
        (
            "INTRODUÇÃO\nTexto.\nDisponibilidade de dados\nOs dados estão no artigo.",
            "INTRODUÇÃO\nTexto.\nDisponibilidade de dados\nOs dados estão no artigo.",
        ),
        (
            "INTRODUÇÃO\nTexto.\nReferências\nSmith 2020",
            "INTRODUÇÃO\nTexto.",
        ),
        (
            "Introduction\nBody.\nConclusions\nThe end.\n"
            "Supplementary Material\nFigure S1 – Extra.",
            "Introduction\nBody.\nConclusions\nThe end.\n"
            "Supplementary Material\nFigure S1 – Extra.",
        ),
        (
            "Introduction\nBody.\nAcknowledgments\nThanks to CNPq.\n"
            "Data Availability\nAvailable upon request.\nReferences\nSmith 2020",
            "Introduction\nBody.\nAcknowledgments\nThanks to CNPq.\n"
            "Data Availability\nAvailable upon request.",
        ),
        (
            "Introduction\nBody.\nAcknowledgments\nThanks.\n"
            "Author Contributions\nAna: writing.\n"
            "Data Availability\nAvailable upon request.\nReferences\nSmith 2020",
            "Introduction\nBody.\nAcknowledgments\nThanks.\n"
            "Data Availability\nAvailable upon request.",
        ),
    ],
)
def test_extract_body_section(text, expected):
    assert extract_body_section(text) == expected


def test_extract_body_section_bn_fixture_docx():
    import zipfile

    from lxml import etree

    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile("fixtures/bn-2025-1828/bn-2025-1828.docx") as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for paragraph in root.iter(f"{W}p"):
        text = "".join((node.text or "") for node in paragraph.iter(f"{W}t")).strip()
        if text:
            paragraphs.append(text)
    body = extract_body_section("\n".join(paragraphs))
    assert "Data Availability" in body
    assert "Author Contributions" not in body
    assert "Acknowledgments" in body


@pytest.mark.django_db
def test_api_docx_marks_body(monkeypatch):
    monkeypatch.setattr(
        "body.data_utils.mark_body",
        lambda text: json.dumps(
            {
                "sections": [
                    {
                        "sec_type": "intro",
                        "title": text.split(chr(10))[0],
                        "content": [{"type": "p", "text": "x"}],
                        "sections": [],
                    }
                ]
            }
        ),
    )
    User = get_user_model()
    user = User.objects.create_user(username="bodydocx", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    uploaded = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(
            ["Título de teste", "Ana Silva", "Introduction", "Corpo do artigo"]
        ),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    response = client.post(
        "/api/v1/body/docx/",
        data={"file": uploaded, "type": "json", "language": "pt"},
        format="multipart",
    )
    assert response.status_code == 200
    assert response.json()["data"]["sections"][0]["title"] == "Introduction"


@pytest.mark.django_db
def test_api_docx_rejects_non_docx():
    User = get_user_model()
    user = User.objects.create_user(username="bodybaddocx", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)
    uploaded = SimpleUploadedFile(
        "article.txt", b"not a docx", content_type="text/plain"
    )
    response = client.post(
        "/api/v1/body/docx/",
        data={"file": uploaded, "type": "json"},
        format="multipart",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_api_docx_rejects_empty_file():
    User = get_user_model()
    user = User.objects.create_user(username="bodyemptydocx", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)
    uploaded = SimpleUploadedFile(
        "article.docx",
        b"",
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    response = client.post(
        "/api/v1/body/docx/",
        data={"file": uploaded, "type": "json"},
        format="multipart",
    )
    assert response.status_code == 400


def test_extract_body_section_keeps_final_considerations_and_skips_editorial():
    text = (
        "Introduction\nStart.\nDiscussion\nTalk.\nFinal considerations\nDone.\n"
        "Submission status\nReceived: 28 Aug. 2025\nAccepted: 16 Dec. 2025\n"
        "Associate editor: Bruno Araujo\nCorrespondence to\nBelém, PA\n"
        "e-mail: author@example.com\nAuthors' contributions\nAna: writing.\n"
        "Data availability\nAll data are included within the article.\n"
        "References\nSmith 2020"
    )
    body = extract_body_section(text)
    assert "Final considerations" in body
    assert "Done." in body
    assert "Data availability" in body
    assert "within the article" in body
    assert "Correspondence to" not in body
    assert "Authors' contributions" not in body
    assert "Associate editor" not in body
    assert "Submission status" not in body


def test_body_from_docx_marks_unnumbered_heading_style_as_subsection():
    uploaded = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(
            [
                "Introduction",
                "Opening.",
                "Material and Methods",
                "Study area",
                "The park is in Pará.",
                "Results",
                "Forty species.",
            ],
            heading_styles={
                "Introduction": "PargrafodaLista",
                "Material and Methods": "PargrafodaLista",
                "Study area": "PargrafodaLista",
                "Results": "PargrafodaLista",
            },
        ),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    body_text, _tables, _figures = body_from_docx_upload(uploaded)
    assert f"{NESTED_HEADING_MARK}Study area" in body_text
    marked = section_from_plain_text(
        "Material and Methods",
        split_body_sections(body_text)[1]["text"],
    )
    assert marked["sections"][0]["title"] == "Study area"
    assert marked["sections"][0]["content"][0]["text"] == "The park is in Pará."


def test_split_body_sections_by_heading():
    parts = split_body_sections(
        "Introduction\nHello.\nMaterial and Methods\nA study.\nResults\nData.\n"
        "Discussion\nTalk.\nConclusions\nDone."
    )
    assert [item["title"] for item in parts] == [
        "Introduction",
        "Material and Methods",
        "Results",
        "Discussion",
        "Conclusions",
    ]


def test_body_from_docx_upload_returns_tables():
    uploaded = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(
            [
                "Title",
                "Introduction",
                "See Table 1.",
                "Table 1. Species recorded.",
            ],
            tables=[[["Family", "Species"], ["Arecaceae", "Mauritia flexuosa"]]],
        ),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    text, tables, figures = body_from_docx_upload(uploaded)
    assert "Introduction" in text
    assert tables
    assert tables[0]["headers"] == ["Family", "Species"]
    assert tables[0]["rows"] == [["Arecaceae", "Mauritia flexuosa"]]
    assert tables[0]["number"] == "1"
    assert figures == []


def test_body_from_docx_upload_harvests_figure_captions_after_references():
    uploaded = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(
            [
                "Title",
                "Introduction",
                "See Figure 1 in the map.",
                "Methods",
                "A study.",
                "References",
                "Smith 2020",
                "FIGURES CAPTIONS",
                (
                    "Figure 1. Cartographic representation map, highlighting "
                    "the location of the ARIE Javari-Buriti."
                ),
            ]
        ),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    text, _tables, figures = body_from_docx_upload(uploaded)
    assert "FIGURES CAPTIONS" not in text
    assert "References" not in text
    assert figures
    assert figures[0]["label"] == "Figure 1"
    assert "Cartographic representation map" in figures[0]["caption"]


@pytest.mark.django_db
def test_api_docx_attaches_fig_href_from_images(monkeypatch):
    from body.tests.test_images import make_tiff_bytes, uploaded_image

    monkeypatch.setattr(
        "body.data_utils.mark_body",
        lambda text: json.dumps(
            {
                "sections": [
                    {
                        "sec_type": "intro",
                        "title": text.split(chr(10))[0],
                        "content": [{"type": "p", "text": "See Figure 1 in the map."}],
                        "sections": [],
                    }
                ]
            }
        ),
    )
    User = get_user_model()
    user = User.objects.create_user(username="bodydocximg", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    uploaded = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(["Title", "Introduction", "See Figure 1 in the map."]),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    response = client.post(
        "/api/v1/body/docx/",
        data={
            "file": uploaded,
            "type": "json",
            "images": uploaded_image("fig-1.tif", make_tiff_bytes()),
        },
        format="multipart",
    )
    assert response.status_code == 200
    figs = [
        block
        for block in response.json()["data"]["sections"][0]["content"]
        if block.get("type") == "fig"
    ]
    assert figs
    assert figs[0]["href"] == "fig-1.jpg"


@pytest.mark.django_db
def test_api_docx_attaches_fig_href_from_images_zip(monkeypatch):
    from body.tests.test_images import make_tiff_bytes

    monkeypatch.setattr(
        "body.data_utils.mark_body",
        lambda text: json.dumps(
            {
                "sections": [
                    {
                        "sec_type": "intro",
                        "title": text.split(chr(10))[0],
                        "content": [{"type": "p", "text": "See Figure 1 in the map."}],
                        "sections": [],
                    }
                ]
            }
        ),
    )
    User = get_user_model()
    user = User.objects.create_user(username="bodydocxzip", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("fig-1.tif", make_tiff_bytes())
        zipped.writestr("notes.txt", "skip")
    archive.seek(0)

    uploaded = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(["Title", "Introduction", "See Figure 1 in the map."]),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    zipped_images = SimpleUploadedFile(
        "figures.zip", archive.getvalue(), content_type="application/zip"
    )
    response = client.post(
        "/api/v1/body/docx/",
        data={
            "file": uploaded,
            "type": "xml",
            "images_zip": zipped_images,
        },
        format="multipart",
    )
    assert response.status_code == 200
    assert 'xlink:href="fig-1.jpg"' in response.json()["data"]

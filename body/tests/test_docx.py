import io
import json
import zipfile
from xml.sax.saxutils import escape

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from body.utils import body_from_docx_upload, extract_body_section, split_body_sections


def make_docx_bytes(paragraphs, tables=None):
    parts = []
    for paragraph in paragraphs:
        parts.append(f"<w:p><w:r><w:t>{escape(paragraph)}</w:t></w:r></w:p>")
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
            "Título\nAna Silva\nIntroduction\nBody of the article\nReferences\nSmith 2020",
            "Introduction\nBody of the article",
        ),
        (
            "Título\n1. Introdução\nCorpo\nAgradecimentos\nCNPq 1",
            "1. Introdução\nCorpo",
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
            "Introduction\nBody.\nConclusions\nThe end.",
        ),
    ],
)
def test_extract_body_section(text, expected):
    assert extract_body_section(text) == expected


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

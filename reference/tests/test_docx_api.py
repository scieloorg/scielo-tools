import io
import zipfile
from xml.sax.saxutils import escape

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from reference.utils.references import extract_references_section


def make_docx_bytes(paragraphs):
    body = "".join(
        f"<w:p><w:r><w:t>{escape(paragraph)}</w:t></w:r></w:p>"
        for paragraph in paragraphs
    )
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
        ("Introduction\nMethods\nResults", ""),
        (
            "Intro\nReferences\nSmith J. Nature. 2024.\nDoe A. Science. 2023.",
            "Smith J. Nature. 2024.\nDoe A. Science. 2023.",
        ),
        (
            "Texto\n5. Referências\nRef A\nRef B",
            "Ref A\nRef B",
        ),
        (
            "Texto\nBibliografia\nRef Unica",
            "Ref Unica",
        ),
    ],
)
def test_extract_references_section(text, expected):
    assert extract_references_section(text) == expected


@pytest.mark.django_db
def test_api_docx_marks_references(monkeypatch):
    monkeypatch.setattr(
        "reference.api.v1.views.resolve_references_result",
        lambda references, user=None, output_type="json": [
            {
                "mixed_citation": citation,
                "data": {"reftype": "journal", "title": citation},
            }
            for citation in references.split("\n")
            if citation.strip()
        ],
    )

    User = get_user_model()
    user = User.objects.create_user(username="docxuser", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    docx_bytes = make_docx_bytes(
        [
            "Introduction",
            "Some body text.",
            "References",
            "Smith J. Nature. 2024.",
            "Doe A. Science. 2023.",
        ]
    )
    upload = SimpleUploadedFile(
        "article.docx",
        docx_bytes,
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )

    response = client.post(
        "/api/v1/reference/docx/",
        data={"file": upload, "type": "json"},
        format="multipart",
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["references"]) == 2
    assert payload["references"][0]["mixed_citation"] == "Smith J. Nature. 2024."
    assert payload["references"][1]["data"]["title"] == "Doe A. Science. 2023."


@pytest.mark.django_db
def test_api_docx_rejects_non_docx():
    User = get_user_model()
    user = User.objects.create_user(username="docxbad", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    upload = SimpleUploadedFile(
        "article.txt",
        b"References\nRef A",
        content_type="text/plain",
    )

    response = client.post(
        "/api/v1/reference/docx/",
        data={"file": upload},
        format="multipart",
    )

    assert response.status_code == 400
    assert "file" in response.json()


@pytest.mark.django_db
def test_api_docx_rejects_missing_references_section():
    User = get_user_model()
    user = User.objects.create_user(username="docxnoref", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    upload = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(["Introduction", "No refs here"]),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )

    response = client.post(
        "/api/v1/reference/docx/",
        data={"file": upload},
        format="multipart",
    )

    assert response.status_code == 400
    assert response.json()["error"] == "No references section found in DOCX"


@pytest.mark.django_db
def test_api_docx_requires_authentication():
    client = APIClient()
    upload = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(["References", "Ref A"]),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )

    response = client.post(
        "/api/v1/reference/docx/",
        data={"file": upload},
        format="multipart",
    )

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_api_docx_get_renders_browsable_form():
    User = get_user_model()
    user = User.objects.create_user(username="docxget", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/v1/reference/docx/")

    assert response.status_code == 200


@pytest.mark.django_db
def test_api_docx_jats_returns_ref_list(monkeypatch):
    monkeypatch.setattr(
        "reference.api.v1.views.resolve_references_result",
        lambda references, user=None, output_type="json": [
            {
                "mixed_citation": "Smith J. Nature. 2024.",
                "data": (
                    '<element-citation publication-type="journal">'
                    "<article-title>Nature</article-title>"
                    "</element-citation>"
                ),
            }
        ],
    )

    User = get_user_model()
    user = User.objects.create_user(username="docxjats", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    upload = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(["Referências", "Smith J. Nature. 2024."]),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )

    response = client.post(
        "/api/v1/reference/docx/",
        data={"file": upload, "type": "jats"},
        format="multipart",
    )

    assert response.status_code == 200
    payload = response.json()
    assert "ref_list" in payload
    assert "<ref-list>" in payload["ref_list"]

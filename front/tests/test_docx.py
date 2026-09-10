import io
import json
import zipfile
from xml.sax.saxutils import escape

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from lxml import etree
from rest_framework.test import APIClient

from front.utils import document_counts, extract_front_section


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
        (
            "Título\nAna Silva\nIntroduction\nBody of the article",
            "Título\nAna Silva",
        ),
        (
            "Título\nAna Silva\n1. Introdução\nCorpo",
            "Título\nAna Silva",
        ),
        (
            "Título\nMethods\nCorpo",
            "Título",
        ),
        (
            "Título\nAna Silva\nIntroduction\nBody\n"
            "Acknowledgments\nFAPESP 2024/23894-1\n"
            "Authors' Contribution\nX wrote the draft\n"
            "Received: 22/12/2025\nAccepted: 21/04/2026\n"
            "Published online: dd/mm/2026",
            "Título\nAna Silva\nAcknowledgments\nFAPESP 2024/23894-1\n"
            "Received: 22/12/2025\nAccepted: 21/04/2026",
        ),
        (
            "Título\nIntrodução\nCorpo\nAgradecimentos\nCNPq 1\n"
            "Referências\nSmith 2020\nRecebido: 07/03/2024",
            "Título\nAgradecimentos\nCNPq 1\nRecebido: 07/03/2024",
        ),
        (
            "Título\nIntroduction\nBody\n"
            "Submitted on 11/06/2025. Accepted on 03/05/2026.",
            "Título\nSubmitted on 11/06/2025. Accepted on 03/05/2026.",
        ),
        (
            "Título\nIntrodução\nCorpo\n"
            "Received: 23 Sept. 2025\nAccepted: 09 Dec. 2025",
            "Título\nReceived: 23 Sept. 2025\nAccepted: 09 Dec. 2025",
        ),
    ],
)
def test_extract_front_section(text, expected):
    assert extract_front_section(text) == expected


def test_document_counts_from_captions_equations_and_references():
    text = (
        "Title\nAna Silva\nIntroduction\nBody of the article\n"
        "Figure 1. Map of the study area.\n"
        "Figure 2. Weight loss after heat treatment.\n"
        "Table 1. Summary of key experimental parameters.\n"
        "Air-dried density (kg/m3)= Equation 1\n"
        "Weight Loss (%) = x 100 Equation 2\n"
        "(%) = x 100Equation 3\n"
        "References\n"
        "Athanázio-Heliodoro JC. Properties of young guapuruvu. 2016.\n"
        "da Silva CBR. Properties of wood. 2018.\n"
        "de Lima Melo LE. Planting density. 2019.\n"
        "Smith J. Another paper. 2020.\n"
    )
    counts = document_counts(text)
    assert counts == {
        "fig_count": "2",
        "table_count": "1",
        "equation_count": "3",
        "ref_count": "4",
    }


def test_document_counts_numbered_refs_stop_at_table():
    text = (
        "Title\nIntroduction\nBody\n"
        "REFERENCES\n"
        "<jrn>1.Araújo SRS. Safety of the elderly. 2020.</jrn>\n"
        "<jrn>2.Orem DE. Self-care. 2006.</jrn>\n"
        "<jrn>3.Teixeira F. Indicadores. 2019.</jrn>\n"
        "Table 1. Sociodemographic characteristics\n"
        "Figure 1. Conceptual model\n"
    )
    counts = document_counts(text)
    assert counts["ref_count"] == "3"
    assert counts["table_count"] == "1"
    assert counts["fig_count"] == "1"


@pytest.mark.django_db
def test_api_docx_marks_front(monkeypatch):
    monkeypatch.setattr(
        "front.data_utils.mark_front",
        lambda text: json.dumps(
            {"titles": [{"kind": "main", "text": text.split(chr(10))[0]}]}
        ),
    )
    User = get_user_model()
    user = User.objects.create_user(username="frontdocx", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    uploaded = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(
            ["Título de teste", "Ana Silva", "Introduction", "Corpo do artigo"]
        ),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response = client.post(
        "/api/v1/front/docx/",
        data={"file": uploaded, "type": "json", "language": "pt"},
        format="multipart",
    )
    assert response.status_code == 200
    assert response.json()["data"]["titles"][0]["text"] == "Título de teste"


@pytest.mark.django_db
def test_api_docx_adds_counts_from_full_document(monkeypatch):
    monkeypatch.setattr(
        "front.data_utils.mark_front",
        lambda text: json.dumps(
            {"titles": [{"kind": "main", "text": text.split(chr(10))[0]}]}
        ),
    )
    User = get_user_model()
    user = User.objects.create_user(username="frontcounts", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)
    uploaded = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(
            [
                "Título de teste",
                "Ana Silva",
                "Introduction",
                "Corpo do artigo",
                "Figure 1. Map.",
                "Figure 2. Chart.",
                "Table 1. Data.",
                "Density = Equation 1",
                "References",
                "Smith J. A paper. 2020.",
                "de Lima A. Another. 2021.",
            ]
        ),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response = client.post(
        "/api/v1/front/docx/",
        data={"file": uploaded, "type": "xml"},
        format="multipart",
    )
    assert response.status_code == 200
    root = etree.fromstring(response.json()["data"].encode("utf-8"))
    counts = root.find(".//counts")
    assert counts.find("fig-count").get("count") == "2"
    assert counts.find("table-count").get("count") == "1"
    assert counts.find("equation-count").get("count") == "1"
    assert counts.find("ref-count").get("count") == "2"


@pytest.mark.django_db
def test_api_docx_rejects_non_docx():
    User = get_user_model()
    user = User.objects.create_user(username="frontbaddocx", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)
    uploaded = SimpleUploadedFile(
        "article.txt", b"not a docx", content_type="text/plain"
    )
    response = client.post(
        "/api/v1/front/docx/",
        data={"file": uploaded, "type": "json"},
        format="multipart",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_api_docx_rejects_empty_file():
    User = get_user_model()
    user = User.objects.create_user(username="frontemptydocx", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)
    uploaded = SimpleUploadedFile(
        "article.docx",
        b"",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    response = client.post(
        "/api/v1/front/docx/",
        data={"file": uploaded, "type": "json"},
        format="multipart",
    )
    assert response.status_code == 400

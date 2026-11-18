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
            "Published online: 17/09/2026",
            "Título\nAna Silva\nAcknowledgments\nFAPESP 2024/23894-1\n"
            "Authors' Contribution\nX wrote the draft\n"
            "Received: 22/12/2025\nAccepted: 21/04/2026\n"
            "Published online: 17/09/2026",
        ),
        (
            "Título\nAna Silva\nIntroduction\nBody\n"
            "Associate Editor\nAlexander Vibrans\n"
            "Author Contributions\n"
            "Karoline A. F. Ribeiro: study design; data analysis\n"
            "Conflicts of Interest\nThe authors declare no conflict.\n"
            "Ethics\nThis study did not involve humans.\n"
            "References\nSmith 2020",
            "Título\nAna Silva\nAssociate Editor\nAlexander Vibrans\n"
            "Author Contributions\n"
            "Karoline A. F. Ribeiro: study design; data analysis\n"
            "Conflicts of Interest\nThe authors declare no conflict.\n"
            "Ethics\nThis study did not involve humans.",
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


def test_extract_front_section_without_body_heading_stops_at_keywords():
    text = (
        "Title\nAna Silva\n"
        "Abstract: Short abstract.\n"
        "Keywords: palms; forest.\n"
        "Resumo: Resumo curto.\n"
        "Palavras-chave: palmeiras; floresta.\n"
        "The high species diversity of the Amazon is known.\n"
        "Plots were installed in the field.\n"
        "Ab'Saber, A. N. (2003). Os dominios. Atelie.\n"
        "Alvares, C. A. (2013a). Modeling temperature. Theoretical.\n"
        "Anderson, J. M. (1993). Tropical soil biology. CAB.\n"
        "Received: 05/08/2025\n"
        "Figure 1. Map of the area.\n"
    )
    front = extract_front_section(text)
    assert "Palavras-chave: palmeiras; floresta." in front
    assert "Received: 05/08/2025" in front
    assert "The high species diversity" not in front
    assert "Ab'Saber" not in front
    assert "Figure 1." not in front


def test_extract_front_section_label_only_keywords_include_next_line():
    text = (
        "Title\n"
        "Abstract\n"
        "Short abstract.\n"
        "Keywords\n"
        "palms; forest\n"
        "The study area is large.\n"
    )
    front = extract_front_section(text)
    assert front == "Title\nAbstract\nShort abstract.\nKeywords\npalms; forest"


def test_extract_front_section_prefers_introduction_over_keywords():
    text = "Title\nAbstract: A.\nKeywords: k.\nIntroduction\nBody of the article."
    assert extract_front_section(text) == "Title\nAbstract: A.\nKeywords: k."


def test_extract_front_section_limits_text_without_any_boundary():
    text = "word " * 5000
    assert len(extract_front_section(text)) == 12000


def test_extract_front_section_moves_unlabeled_editorial_tail():
    text = (
        "Title\n"
        "Abstract: A.\n"
        "Keywords: palms.\n"
        "The study sampled plots.\n"
        "The authors would like to express their gratitude for the field.\n"
        "Alexander Vibrans\n"
        "Ana Silva: study design; data analysis; manuscript revision.\n"
        "The authors declare no conflict of interest.\n"
        "This study did not involve human beings.\n"
        "The datasets generated during the study are available.\n"
        "Ab'Saber, A. N. (2003). Title. Publisher.\n"
        "Alvares, C. A. (2013). Title. Publisher.\n"
        "Anderson, J. M. (1993). Title. Publisher.\n"
        "Received: 05/08/2025\n"
    )
    front = extract_front_section(text)
    assert "Keywords: palms." in front
    assert "Alexander Vibrans" in front
    assert "Ana Silva: study design" in front
    assert "no conflict of interest" in front
    assert "did not involve human beings" in front
    assert "would like to express" in front
    assert "Received: 05/08/2025" in front
    assert "The study sampled plots." not in front
    assert "datasets generated" not in front
    assert "Ab'Saber" not in front


def test_extract_front_section_keeps_correspondence_and_inline_editor():
    text = (
        "Title\nIntroduction\nBody.\nFinal considerations\nDone.\n"
        "Received: 28 Aug. 2025\nAccepted: 16 Dec. 2025\n"
        "Associate editor: Bruno Araujo: http://orcid.org/0000-0003-0288-0024\n"
        "Correspondence to\nBelém, PA\ne-mail: author@example.com\n"
        "Authors' contributions\nAna: writing.\n"
        "Data availability\nIncluded within the article.\n"
        "References\nSmith 2020"
    )
    front = extract_front_section(text)
    assert "Correspondence to" in front
    assert "Belém, PA" in front
    assert "author@example.com" in front
    assert "Associate editor: Bruno Araujo" in front
    assert "Received: 28 Aug. 2025" in front
    assert "Included within the article." not in front


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


def test_document_counts_unsectioned_apa_references():
    text = (
        "Title\nAbstract: A.\nKeywords: k.\n"
        "Body paragraph one.\nBody paragraph two.\n"
        "Ab'Saber, A. N. (2003). Title. Publisher.\n"
        "Alvares, C. A. (2013). Title. Publisher.\n"
        "Anderson, J. M. (1993). Title. Publisher.\n"
        "Received: 05/08/2025\n"
        "Figure 1. Map of the area.\n"
    )
    counts = document_counts(text)
    assert counts["ref_count"] == "3"
    assert counts["fig_count"] == "1"


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

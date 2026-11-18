import io
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from lxml import etree
from rest_framework.test import APIClient

from body.data_utils import get_body_xml
from body.utils import (
    NESTED_HEADING_MARK,
    apply_body_rules,
    body_from_docx_upload,
    extract_body_section,
    iter_content_lists,
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


def test_extract_body_section_without_heading_starts_after_keywords():
    text = (
        "Title\nAna Silva\n"
        "Abstract: Short abstract.\n"
        "Keywords: palms; forest.\n"
        "Palavras-chave: palmeiras; floresta.\n"
        "The high species diversity of the Amazon is known.\n"
        "Plots were installed in the field.\n"
        "Ab'Saber, A. N. (2003). Os dominios. Atelie.\n"
        "Alvares, C. A. (2013a). Modeling temperature. Theoretical.\n"
        "Anderson, J. M. (1993). Tropical soil biology. CAB.\n"
        "Received: 05/08/2025\n"
    )
    body = extract_body_section(text)
    assert body == (
        "The high species diversity of the Amazon is known.\n"
        "Plots were installed in the field."
    )


def test_extract_body_section_stops_at_unheaded_references():
    text = (
        "Introduction\nBody of the article.\n"
        "Ab'Saber, A. N. (2003). Os dominios. Atelie.\n"
        "Alvares, C. A. (2013a). Modeling temperature. Theoretical.\n"
        "Anderson, J. M. (1993). Tropical soil biology. CAB.\n"
    )
    assert extract_body_section(text) == "Introduction\nBody of the article."


def test_extract_body_section_stops_at_unheaded_numbered_references():
    text = (
        "Title\nAbstract: A.\nKeywords: k.\nThe study sampled 24 plots.\n"
        "1. Smith J. Safety of the elderly. 2020.\n"
        "2. Orem DE. Self-care. 2006.\n"
        "3. Teixeira F. Indicadores. 2019.\n"
    )
    assert extract_body_section(text) == "The study sampled 24 plots."


def test_extract_body_section_drops_unlabeled_editorial_tail():
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
    )
    assert extract_body_section(text) == (
        "The study sampled plots.\n"
        "The authors would like to express their gratitude for the field.\n"
        "The datasets generated during the study are available."
    )


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
    assert tables[0]["label"] == "Table 1"
    assert tables[0]["caption"] == "Species recorded."
    assert figures == []


def test_body_from_docx_upload_reads_spanish_tabla_caption():
    uploaded = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(
            [
                "Título",
                "Introducción",
                "El portal presenta una usabilidad óptima (ver tabla 1).",
                "Tabla 1. Confianza en shopDisney.es, dimensión Diseño y Navegación",
            ],
            tables=[[["Indicadores", "Sí", "No"], ["Protocolo seguro", "https", ""]]],
        ),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    text, tables, figures = body_from_docx_upload(uploaded)
    assert "Tabla 1. Confianza en shopDisney.es" in text
    assert tables[0]["number"] == "1"
    assert tables[0]["label"] == "Tabla 1"
    assert (
        tables[0]["caption"]
        == "Confianza en shopDisney.es, dimensión Diseño y Navegación"
    )
    assert tables[0]["headers"] == ["Indicadores", "Sí", "No"]
    assert tables[0]["rows"] == [["Protocolo seguro", "https", ""]]
    assert figures == []


def test_section_from_plain_text_marks_spanish_table_and_fuente():
    marked = section_from_plain_text(
        "Introducción",
        "\n".join(
            [
                "El portal presenta una usabilidad óptima (ver tabla 1).",
                "Tabla 1. Confianza en shopDisney.es, dimensión Diseño y Navegación",
                "Fuente: elaboración propia.",
            ]
        ),
    )
    wraps = [block for block in marked["content"] if block.get("type") == "table-wrap"]
    assert len(wraps) == 1
    assert wraps[0]["label"] == "Tabla 1"
    assert wraps[0]["id"] == "t1"
    assert (
        wraps[0]["caption"]
        == "Confianza en shopDisney.es, dimensión Diseño y Navegación"
    )
    assert wraps[0]["attrib"] == "elaboración propia."
    texts = [
        block.get("text") for block in marked["content"] if block.get("type") == "p"
    ]
    assert not any(str(text).startswith("Tabla") for text in texts)
    assert not any(str(text).startswith("Fuente") for text in texts)


def test_section_from_plain_text_keeps_table_tabela_and_quadro_labels():
    table = section_from_plain_text("Introduction", "Table 3. Species recorded.")
    tabela = section_from_plain_text("Introdução", "Tabela 2. Espécies registradas.")
    quadro = section_from_plain_text("Introdução", "Quadro 4. Indicadores.")
    assert table["content"][0]["label"] == "Table 3"
    assert tabela["content"][0]["label"] == "Tabela 2"
    assert quadro["content"][0]["label"] == "Quadro 4"


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


def marked_body_from_docx(path):
    uploaded = SimpleUploadedFile(
        "article.docx",
        Path(path).read_bytes(),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    text, tables, _figures = body_from_docx_upload(uploaded)
    sections = [
        section_from_plain_text(part["title"], part["text"])
        for part in split_body_sections(text)
    ]
    return apply_body_rules({"sections": sections}, text, tables=tables)


def test_article_3_docx_marks_display_and_inline_formulas():
    marked = marked_body_from_docx("fixtures/!bulk/formula/article_3.docx")
    blocks = []
    for section in marked["sections"]:
        for content in iter_content_lists(section):
            blocks.extend(content)
    displayed = [block for block in blocks if block.get("type") == "disp-formula"]
    assert [(block.get("id"), block.get("label")) for block in displayed] == [
        ("e1", "(1)"),
        ("e2", "(2)"),
        ("e3", "(3)"),
    ]
    inlines = []
    for block in blocks:
        if block.get("type") != "p":
            continue
        inlines.extend(block.get("formulas") or [])
    assert [item["id"] for item in inlines] == ["e4", "e5", "e6"]
    mentions = []
    for block in blocks:
        if block.get("type") != "p":
            continue
        for xref in block.get("xrefs") or []:
            if xref.get("ref_type") == "disp-formula":
                mentions.append((xref["rid"], xref["text"]))
    assert mentions == [
        ("e1", "Equation (1)"),
        ("e2", "Equation (2)"),
        ("e3", "Equation (3)"),
        ("e3", "Equation (3)"),
    ]
    xml = get_body_xml(marked)
    root = etree.fromstring(xml.encode("utf-8"))
    mml = "http://www.w3.org/1998/Math/MathML"
    formulas = root.findall(".//disp-formula")
    assert [item.get("id") for item in formulas] == ["e1", "e2", "e3"]
    assert formulas[0].find(f".//{{{mml}}}mfrac") is not None
    assert formulas[0].find(f".//{{{mml}}}msqrt") is not None
    assert formulas[0].find(f"{{{mml}}}math").get("id") == "m1"
    names = [item.text for item in formulas[0].findall(f".//{{{mml}}}mi")]
    assert "a" in names and "c" in names and "ac" not in names
    assert formulas[1].find(f".//{{{mml}}}msup") is not None
    assert formulas[1].find(f".//{{{mml}}}mfrac") is not None
    assert formulas[2].find(f".//{{{mml}}}mo").text == "⋃"
    inline_nodes = root.findall(".//inline-formula")
    assert [item.get("id") for item in inline_nodes] == ["e4", "e5", "e6"]
    assert "B" in "".join(inline_nodes[0].itertext())
    assert "\u2063" not in xml
    xrefs = root.findall(".//xref[@ref-type='disp-formula']")
    assert [item.get("rid") for item in xrefs] == ["e1", "e2", "e3", "e3"]
    assert xrefs[0].text == "Equation (1)"


def test_article_1_docx_marks_labeled_formulas_and_portuguese_mentions():
    marked = marked_body_from_docx("fixtures/!bulk/formula/article_1.docx")
    xml = get_body_xml(marked)
    root = etree.fromstring(xml.encode("utf-8"))
    mml = "http://www.w3.org/1998/Math/MathML"
    formulas = root.findall(".//disp-formula")
    assert [(item.get("id"), item.findtext("label")) for item in formulas] == [
        ("e1", "(1)"),
        ("e2", "(2)"),
    ]
    assert formulas[0].find(f".//{{{mml}}}msub") is not None
    base = formulas[0].find(f".//{{{mml}}}mi")
    assert base.text == "ADM"
    assert base.get("mathvariant") == "normal"
    mentions = [
        (item.get("rid"), item.text)
        for item in root.findall(".//xref[@ref-type='disp-formula']")
    ]
    assert mentions == [("e1", "equação (1)"), ("e2", "equação (2)")]

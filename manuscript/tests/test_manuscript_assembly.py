import os
import tempfile
import zipfile
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from docx import Document as DocxDocument

from body.data_utils import get_body_xml
from front.data_utils import get_front_xml
from manuscript.models import Manuscript, ManuscriptFigureFile, ManuscriptReference
from manuscript.services.assembly import (
    AssemblyError,
    assemble_manuscript_xml,
    build_sps_zip,
    generate_packtools_pdf,
    refresh_assembled_xml,
)
from manuscript.services.marking import (
    save_body_marked,
    save_front_marked,
    save_references_from_payload,
)

User = get_user_model()


class ManuscriptAssemblyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="secret")
        self.manuscript = Manuscript.objects.create(
            title="Assembly test",
            creator=self.user,
            front_marked_xml=get_front_xml(
                {
                    "titles": [
                        {"kind": "main", "text": "Assembly title", "language": "en"}
                    ],
                }
            ),
            body_marked_xml=get_body_xml(
                {
                    "sections": [
                        {
                            "title": "Intro",
                            "content": [{"type": "p", "text": "Paragraph."}],
                            "sections": [],
                        }
                    ]
                }
            ),
        )
        ManuscriptReference.objects.create(
            manuscript=self.manuscript,
            mixed_citation="Author A. Article.",
            marked={"reftype": "journal", "source": "Journal", "date": "2024"},
            marked_xml=(
                '<element-citation publication-type="journal">'
                "<source>Journal</source><year>2024</year>"
                "</element-citation>"
            ),
            sort_order=0,
        )

    def test_assemble_manuscript_xml(self):
        xml = assemble_manuscript_xml(self.manuscript)
        self.assertIn("Assembly title", xml)
        self.assertIn("Paragraph.", xml)
        self.assertIn("<article", xml)

    def test_refresh_assembled_xml_skips_when_body_missing(self):
        self.manuscript.body_marked_xml = ""
        self.manuscript.save(update_fields=["body_marked_xml"])
        result = refresh_assembled_xml(self.manuscript)
        self.manuscript.refresh_from_db()
        self.assertIsNone(result)
        self.assertEqual(self.manuscript.assembled_xml, "")

    def test_save_front_marked_skips_assembly_when_incomplete(self):
        incomplete = Manuscript.objects.create(
            title="Incomplete",
            creator=self.user,
        )
        save_front_marked(
            incomplete,
            {"titles": [{"kind": "main", "text": "Only front", "language": "en"}]},
            user=self.user,
        )
        incomplete.refresh_from_db()
        self.assertIn("Only front", incomplete.front_marked_xml)
        self.assertEqual(incomplete.assembled_xml, "")

    def test_save_front_marked_updates_assembled_xml_when_complete(self):
        save_front_marked(
            self.manuscript,
            {
                "titles": [
                    {"kind": "main", "text": "Updated assembly title", "language": "en"}
                ]
            },
            user=self.user,
        )
        self.manuscript.refresh_from_db()
        self.assertIn("Updated assembly title", self.manuscript.assembled_xml)
        self.assertIn("Paragraph.", self.manuscript.assembled_xml)
        self.assertNotIn("Assembly title", self.manuscript.assembled_xml)

    def test_save_body_marked_updates_assembled_xml_when_complete(self):
        save_body_marked(
            self.manuscript,
            {
                "sections": [
                    {
                        "title": "Intro",
                        "content": [{"type": "p", "text": "Updated paragraph."}],
                        "sections": [],
                    }
                ]
            },
            user=self.user,
        )
        self.manuscript.refresh_from_db()
        self.assertIn("Updated paragraph.", self.manuscript.assembled_xml)
        self.assertIn("Assembly title", self.manuscript.assembled_xml)
        self.assertNotIn(">Paragraph.<", self.manuscript.assembled_xml)

    def test_save_references_from_payload_updates_assembled_xml_when_complete(self):
        save_references_from_payload(
            self.manuscript,
            [
                {
                    "mixed_citation": "Author B. Updated article.",
                    "marked": {
                        "reftype": "journal",
                        "source": "Updated Journal",
                        "date": "2025",
                    },
                }
            ],
            user=self.user,
        )
        self.manuscript.refresh_from_db()
        self.assertIn("Updated Journal", self.manuscript.assembled_xml)
        self.assertIn("Assembly title", self.manuscript.assembled_xml)
        self.assertNotIn(">Journal<", self.manuscript.assembled_xml)

    def test_build_sps_zip_includes_figure_files(self):
        fig1 = ManuscriptFigureFile(
            manuscript=self.manuscript,
            number=1,
            href="fig-1.jpg",
            original_name="fig-1.tif",
            sort_order=1,
        )
        fig1.file.save("fig-1.jpg", ContentFile(b"jpeg-one"), save=True)
        fig2 = ManuscriptFigureFile(
            manuscript=self.manuscript,
            number=2,
            href="fig-2.jpg",
            original_name="fig-2.jpg",
            sort_order=2,
        )
        fig2.file.save("fig-2.jpg", ContentFile(b"jpeg-two"), save=True)
        document = build_sps_zip(self.manuscript)
        with document.file.open("rb") as fh:
            with zipfile.ZipFile(fh) as archive:
                names = set(archive.namelist())
                self.assertIn("fig-1.jpg", names)
                self.assertIn("fig-2.jpg", names)
                self.assertEqual(archive.read("fig-1.jpg"), b"jpeg-one")
                self.assertEqual(archive.read("fig-2.jpg"), b"jpeg-two")
                xml_names = [name for name in names if name.endswith(".xml")]
                self.assertEqual(len(xml_names), 1)

    def test_build_sps_zip_keeps_existing_assembled_xml(self):
        self.manuscript.assembled_xml = (
            "<article><title>Manually edited XML</title></article>"
        )
        self.manuscript.save(update_fields=["assembled_xml"])
        document = build_sps_zip(self.manuscript)
        self.manuscript.refresh_from_db()
        self.assertIn("Manually edited XML", self.manuscript.assembled_xml)
        self.assertNotIn("Assembly title", self.manuscript.assembled_xml)
        with document.file.open("rb") as fh:
            with zipfile.ZipFile(fh) as archive:
                xml_names = [
                    name for name in archive.namelist() if name.endswith(".xml")
                ]
                self.assertEqual(len(xml_names), 1)
                packed = archive.read(xml_names[0]).decode("utf-8")
                self.assertIn("Manually edited XML", packed)
                self.assertNotIn("Assembly title", packed)

    def test_build_sps_zip_omits_pdf_by_default(self):
        with patch("manuscript.services.assembly.generate_packtools_pdf") as mock_pdf:
            document = build_sps_zip(self.manuscript)
        mock_pdf.assert_not_called()
        with document.file.open("rb") as fh:
            with zipfile.ZipFile(fh) as archive:
                names = archive.namelist()
                self.assertFalse(any(name.endswith(".pdf") for name in names))
                self.assertFalse(any(name.endswith(".docx") for name in names))

    def test_build_sps_zip_includes_pdf_when_requested(self):
        fig = ManuscriptFigureFile(
            manuscript=self.manuscript,
            number=1,
            href="fig-1.jpg",
            original_name="fig-1.jpg",
            sort_order=1,
        )
        fig.file.save("fig-1.jpg", ContentFile(b"jpeg-one"), save=True)
        with patch(
            "manuscript.services.assembly.generate_packtools_pdf",
            return_value=b"%PDF-fake",
        ) as mock_pdf:
            document = build_sps_zip(self.manuscript, include_pdf=True)
        mock_pdf.assert_called_once()
        with document.file.open("rb") as fh:
            with zipfile.ZipFile(fh) as archive:
                names = set(archive.namelist())
                self.assertIn("fig-1.jpg", names)
                self.assertIn("Assembly-test.pdf", names)
                self.assertEqual(archive.read("Assembly-test.pdf"), b"%PDF-fake")
                self.assertFalse(any(name.endswith(".docx") for name in names))

    def test_build_sps_zip_replaces_previous_file_on_disk(self):
        first = build_sps_zip(self.manuscript)
        previous_name = first.file.name
        previous_path = first.file.path
        build_sps_zip(self.manuscript)
        self.manuscript.refresh_from_db()
        current = self.manuscript.sps_package
        self.assertTrue(os.path.exists(current.file.path))
        if current.file.name != previous_name:
            self.assertFalse(os.path.exists(previous_path))

    def test_build_sps_zip_pdf_failure_leaves_package_unchanged(self):
        existing = build_sps_zip(self.manuscript)
        existing_pk = existing.pk
        with existing.file.open("rb") as fh:
            previous = fh.read()
        with patch(
            "manuscript.services.assembly.generate_packtools_pdf",
            side_effect=AssemblyError("PDF generation failed"),
        ):
            with self.assertRaises(AssemblyError):
                build_sps_zip(self.manuscript, include_pdf=True)
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.sps_package_id, existing_pk)
        with self.manuscript.sps_package.file.open("rb") as fh:
            self.assertEqual(fh.read(), previous)

    def test_generate_packtools_pdf_reads_converted_file(self):
        fig = ManuscriptFigureFile(
            manuscript=self.manuscript,
            number=1,
            href="fig-1.jpg",
            original_name="fig-1.jpg",
            sort_order=1,
        )
        fig.file.save("fig-1.jpg", ContentFile(b"jpeg-one"), save=True)
        document = MagicMock()
        captured = {}

        def fake_convert(docx_path, *args, **kwargs):
            pdf_path = docx_path[:-5] + ".pdf"
            with open(pdf_path, "wb") as fh:
                fh.write(b"%PDF-from-mock")
            return pdf_path

        def capture_pipeline(xml_tree, data):
            captured["layout"] = data["base_layout"]
            layout_doc = DocxDocument(data["base_layout"])
            captured["styles"] = [style.name for style in layout_doc.styles]
            return document

        with (
            patch(
                "manuscript.services.assembly.packtools_xml_utils.get_xml_tree"
            ) as mock_tree,
            patch(
                "manuscript.services.assembly.packtools_docx.pipeline_docx",
                side_effect=capture_pipeline,
            ),
            patch(
                "manuscript.services.assembly.packtools_file_utils.convert_docx_to_pdf",
                side_effect=fake_convert,
            ),
        ):
            pdf_bytes = generate_packtools_pdf(
                "<article/>",
                "Assembly-test.xml",
                list(self.manuscript.figure_files.all()),
            )
        self.assertEqual(pdf_bytes, b"%PDF-from-mock")
        mock_tree.assert_called_once()
        document.save.assert_called_once()
        self.assertTrue(captured["layout"].endswith("_scielo-layout.docx"))
        self.assertIn("SCL Journal Title Char", captured["styles"])

    def test_generate_packtools_pdf_uses_configured_layout(self):
        layout_path = os.path.join(tempfile.gettempdir(), "custom-pdf-layout.docx")
        DocxDocument().save(layout_path)
        self.addCleanup(lambda: os.path.exists(layout_path) and os.remove(layout_path))
        document = MagicMock()
        captured = {}

        def fake_convert(docx_path, *args, **kwargs):
            pdf_path = docx_path[:-5] + ".pdf"
            with open(pdf_path, "wb") as fh:
                fh.write(b"%PDF-from-mock")
            return pdf_path

        def capture_pipeline(xml_tree, data):
            captured["layout"] = data["base_layout"]
            return document

        with (
            override_settings(PACKTOOLS_PDF_LAYOUT=layout_path),
            patch("manuscript.services.assembly.packtools_xml_utils.get_xml_tree"),
            patch(
                "manuscript.services.assembly.packtools_docx.pipeline_docx",
                side_effect=capture_pipeline,
            ),
            patch(
                "manuscript.services.assembly.packtools_file_utils.convert_docx_to_pdf",
                side_effect=fake_convert,
            ),
        ):
            generate_packtools_pdf("<article/>", "x.xml", [])
        self.assertEqual(captured["layout"], layout_path)

    def test_generate_packtools_pdf_wraps_packtools_errors(self):
        with patch(
            "manuscript.services.assembly.packtools_xml_utils.get_xml_tree",
            side_effect=RuntimeError("libreoffice missing"),
        ):
            with self.assertRaises(AssemblyError) as ctx:
                generate_packtools_pdf("<article/>", "x.xml", [])
        self.assertIn("PDF generation failed", str(ctx.exception))

    def test_generate_packtools_pdf_accepts_body_wider_than_header(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article" xml:lang="en">
  <front>
    <journal-meta>
      <journal-title-group>
        <journal-title>Test Journal</journal-title>
      </journal-title-group>
    </journal-meta>
    <article-meta>
      <article-id pub-id-type="doi">10.1590/test</article-id>
      <article-categories>
        <subj-group subj-group-type="heading">
          <subject>Article</subject>
        </subj-group>
      </article-categories>
      <title-group>
        <article-title>Wide table article</article-title>
      </title-group>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Data Availability</title>
      <table-wrap>
        <label>Table 1</label>
        <caption><title>Dataset</title></caption>
        <table>
          <thead>
            <tr><th>A</th><th>B</th></tr>
          </thead>
          <tbody>
            <tr><td>1</td><td>2</td><td>3</td><td>4</td><td>5</td></tr>
          </tbody>
        </table>
      </table-wrap>
    </sec>
  </body>
  <back>
    <ref-list>
      <ref>
        <mixed-citation>Author A. Article.</mixed-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""

        def fake_convert(docx_path, *args, **kwargs):
            pdf_path = docx_path[:-5] + ".pdf"
            with open(pdf_path, "wb") as fh:
                fh.write(b"%PDF-from-mock")
            return pdf_path

        with patch(
            "manuscript.services.assembly.packtools_file_utils.convert_docx_to_pdf",
            side_effect=fake_convert,
        ):
            pdf_bytes = generate_packtools_pdf(xml, "wide-table.xml", [])
        self.assertEqual(pdf_bytes, b"%PDF-from-mock")

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from wagtail.documents.models import Document

from front.tests.test_docx import make_docx_bytes
from manuscript.models import Manuscript, ManuscriptFigureFile
from manuscript.services.marking import (
    MarkingError,
    mark_body,
    mark_front,
    mark_references,
    save_front_marked,
    save_references_from_payload,
    save_references_marked_xml,
)
from reference.data_utils import build_ref_list

User = get_user_model()


class MarkingSnapshotTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="secret")
        self.manuscript = Manuscript.objects.create(
            title="Snapshot test",
            creator=self.user,
        )

    def test_save_front_marked_updates_xml_snapshot(self):
        marked = {
            "titles": [{"kind": "main", "text": "Updated title", "language": "en"}],
        }
        save_front_marked(self.manuscript, marked, user=self.user)
        self.manuscript.refresh_from_db()
        self.assertEqual(
            self.manuscript.front_marked["titles"][0]["text"],
            "Updated title",
        )
        self.assertIn("Updated title", self.manuscript.front_marked_xml)

    def test_save_front_marked_keeps_history_and_counts_in_xml(self):
        save_front_marked(
            self.manuscript,
            {
                "titles": [{"kind": "main", "text": "With extras", "language": "en"}],
                "history": [
                    {"type": "received", "day": "05", "month": "08", "year": "2025"},
                    {"type": "accepted", "day": "27", "month": "03", "year": "2026"},
                ],
                "counts": {
                    "fig_count": "5",
                    "table_count": "3",
                    "equation_count": "0",
                    "ref_count": "97",
                },
            },
            user=self.user,
        )
        self.manuscript.refresh_from_db()
        xml = self.manuscript.front_marked_xml
        self.assertIn("<history>", xml)
        self.assertIn('date-type="received"', xml)
        self.assertIn('date-type="accepted"', xml)
        self.assertIn("<counts>", xml)
        self.assertIn('<fig-count count="5"/>', xml)
        self.assertIn('<ref-count count="97"/>', xml)

    @patch("manuscript.services.marking.resolve_front_result")
    def test_mark_front_passes_stored_counts(self, mock_resolve):
        def fake_resolve(
            text, user=None, output_type="json", language=None, counts=None
        ):
            data = {"titles": [{"kind": "main", "text": "Hello", "language": "en"}]}
            if counts:
                data["counts"] = counts
            return {"data": data}

        mock_resolve.side_effect = fake_resolve
        self.manuscript.front_source_text = "Hello front"
        self.manuscript.front_counts = {"fig_count": "2", "ref_count": "10"}
        self.manuscript.save()
        mark_front(self.manuscript, user=self.user)
        self.assertEqual(
            mock_resolve.call_args.kwargs["counts"],
            {"fig_count": "2", "ref_count": "10"},
        )
        self.manuscript.refresh_from_db()
        self.assertIn('<fig-count count="2"/>', self.manuscript.front_marked_xml)
        self.assertIn('<ref-count count="10"/>', self.manuscript.front_marked_xml)

    @patch("manuscript.services.marking.resolve_front_result")
    def test_mark_front_loads_counts_from_source_document(self, mock_resolve):
        def fake_resolve(
            text, user=None, output_type="json", language=None, counts=None
        ):
            data = {"titles": [{"kind": "main", "text": "Hello", "language": "en"}]}
            if counts:
                data["counts"] = counts
            return {"data": data}

        mock_resolve.side_effect = fake_resolve
        upload = SimpleUploadedFile(
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
                    "References",
                    "Smith J. A paper. 2020.",
                    "de Lima A. Another. 2021.",
                ]
            ),
            content_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        )
        document = Document(title="article.docx")
        document.file.save("article.docx", upload, save=True)
        self.manuscript.source_document = document
        self.manuscript.front_source_text = "Título de teste"
        self.manuscript.front_counts = {}
        self.manuscript.save()
        mark_front(self.manuscript, user=self.user)
        counts = mock_resolve.call_args.kwargs["counts"]
        self.assertEqual(counts["fig_count"], "2")
        self.assertEqual(counts["table_count"], "1")
        self.assertEqual(counts["ref_count"], "2")
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.front_counts["fig_count"], "2")
        self.assertIn('<fig-count count="2"/>', self.manuscript.front_marked_xml)

    @patch("manuscript.services.marking.resolve_body_result")
    def test_mark_body_passes_stored_image_hrefs(self, mock_resolve):
        mock_resolve.return_value = {
            "data": {
                "sections": [
                    {
                        "title": "Intro",
                        "content": [
                            {
                                "type": "fig",
                                "id": "f1",
                                "label": "Figure 1",
                                "caption": "Map",
                                "href": "fig-1.jpg",
                            }
                        ],
                        "sections": [],
                    }
                ]
            }
        }
        self.manuscript.body_source_text = "See Figure 1."
        self.manuscript.save(update_fields=["body_source_text"])
        figure = ManuscriptFigureFile(
            manuscript=self.manuscript,
            number=1,
            href="fig-1.jpg",
            original_name="fig-1.tif",
            sort_order=1,
        )
        figure.file.save("fig-1.jpg", ContentFile(b"\xff\xd8fakejpeg"), save=True)
        mark_body(self.manuscript, user=self.user)
        self.assertEqual(
            mock_resolve.call_args.kwargs["image_hrefs"],
            {"1": "fig-1.jpg"},
        )
        self.manuscript.refresh_from_db()
        self.assertIn("fig-1.jpg", self.manuscript.body_marked_xml)

    @patch("manuscript.services.marking.resolve_references_result")
    def test_mark_references_uses_batch_resolve(self, mock_resolve):
        mock_resolve.return_value = [
            {
                "mixed_citation": "Smith J. Nature. 2024.",
                "data": {"reftype": "journal", "source": "Nature"},
            },
            {
                "mixed_citation": "Doe A. Book. 2023.",
                "data": {"reftype": "book", "source": "Book"},
            },
        ]
        self.manuscript.references_source_text = (
            "Smith J. Nature. 2024.\nDoe A. Book. 2023."
        )
        self.manuscript.save(update_fields=["references_source_text"])
        mark_references(self.manuscript, user=self.user)
        mock_resolve.assert_called_once()
        self.assertEqual(
            mock_resolve.call_args.args[0],
            ["Smith J. Nature. 2024.", "Doe A. Book. 2023."],
        )
        self.assertEqual(self.manuscript.references.count(), 2)
        first = self.manuscript.references.order_by("sort_order").first()
        self.assertEqual(first.mixed_citation, "Smith J. Nature. 2024.")
        self.assertIn("Nature", first.marked_xml)

    @patch("manuscript.services.marking.resolve_references_result")
    def test_mark_references_raises_when_batch_empty(self, mock_resolve):
        mock_resolve.return_value = []
        self.manuscript.references_source_text = "Smith J. Nature. 2024."
        self.manuscript.save(update_fields=["references_source_text"])
        with self.assertRaises(MarkingError):
            mark_references(self.manuscript, user=self.user)

    def test_save_references_from_payload(self):
        save_references_from_payload(
            self.manuscript,
            [
                {
                    "mixed_citation": "Author A. Article.",
                    "marked": {"reftype": "journal", "source": "Journal"},
                }
            ],
            user=self.user,
        )
        self.assertEqual(self.manuscript.references.count(), 1)
        ref = self.manuscript.references.first()
        self.assertEqual(ref.mixed_citation, "Author A. Article.")
        self.assertIn("Journal", ref.marked_xml)

    def test_save_references_marked_xml_updates_references(self):
        save_references_marked_xml(
            self.manuscript,
            build_ref_list(
                [
                    {
                        "mixed_citation": "Author B. Updated reference.",
                        "data": (
                            '<element-citation publication-type="journal">'
                            "<source>Updated Journal</source>"
                            "</element-citation>"
                        ),
                    }
                ]
            ),
            user=self.user,
        )
        self.assertEqual(self.manuscript.references.count(), 1)
        ref = self.manuscript.references.first()
        self.assertEqual(ref.mixed_citation, "Author B. Updated reference.")
        self.assertIn("Updated Journal", ref.marked_xml)

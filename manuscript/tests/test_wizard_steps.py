import io
import json
import zipfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import override
from lxml import etree
from PIL import Image

from body.data_utils import get_body_xml
from front.data_utils import get_front_xml
from manuscript.models import Manuscript, ManuscriptReference, ManuscriptStatus
from manuscript.services.marking import MarkingError
from reference.data_utils import build_ref_list


def jpeg_upload(name, color=(0, 255, 0)):
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color=color).save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


class WizardStepLabelTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)
        self.manuscript = Manuscript.objects.create(
            title="bn-2025-1834",
            status=ManuscriptStatus.FRONT,
            creator=user,
        )

    def test_wizard_nav_uses_front_body_back_validate_package(self):
        response = self.client.get(
            reverse("manuscript_step_front", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(">Front</a>", content)
        self.assertIn(">Body</a>", content)
        self.assertIn(">Back</a>", content)
        self.assertIn(">Validar</a>", content)
        self.assertIn(">Pacote</a>", content)
        self.assertEqual(content.count('class="manuscript-wizard__step-arrow"'), 4)
        self.assertNotIn(">Corpo</a>", content)
        self.assertNotIn(">Verso</a>", content)
        self.assertContains(
            response, reverse("manuscript_step_package", args=[self.manuscript.pk])
        )
        self.assertIn('class="manuscript-wizard__toolbar"', content)
        self.assertIn('class="manuscript-wizard__preview-title"', content)
        toolbar_chunk = content.split('class="manuscript-wizard__toolbar"', 1)[1]
        toolbar_chunk = toolbar_chunk.split(
            'class="manuscript-wizard__preview-title"', 1
        )[0]
        self.assertIn(">Front</a>", toolbar_chunk)
        self.assertNotIn("Preview", toolbar_chunk)
        extra = content.split('class="manuscript-wizard__editor-extra"', 1)[1]
        self.assertIn("Front editor", extra)
        editor = content.split('class="manuscript-wizard__editor"', 1)[1]
        editor = editor.split('class="manuscript-wizard__preview"', 1)[0]
        self.assertIn("Front source", editor)
        self.assertNotIn("Front editor", editor)

    def test_portuguese_back_term_is_not_verso(self):
        with override("pt-br"):
            texts = [
                str(ManuscriptStatus.BACK.label),
                _("Back approved at"),
                _("Cannot approve back from current status"),
                _("Approve the back step to assemble XML."),
                _("Back approved and XML assembled."),
            ]
        for text in texts:
            self.assertNotIn("verso", text.lower())
            self.assertIn("back", text.lower())

    def test_front_step_i18n_includes_history_and_counts(self):
        response = self.client.get(
            reverse("manuscript_step_front", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('"addHistoryDate"', content)
        self.assertIn('"figCount"', content)
        self.assertIn('"received"', content)
        self.assertIn('"counts"', content)

    @patch("manuscript.services.marking.resolve_front_result")
    def test_mark_uses_persisted_front_counts(self, mock_resolve):
        def fake_resolve(
            text, user=None, output_type="json", language=None, counts=None
        ):
            data = {
                "titles": [{"kind": "main", "text": "Hello", "language": "en"}],
                "history": [
                    {"type": "received", "day": "05", "month": "08", "year": "2025"}
                ],
            }
            if counts:
                data["counts"] = counts
            return {"data": data}

        mock_resolve.side_effect = fake_resolve
        self.manuscript.front_source_text = "Hello front text"
        self.manuscript.front_counts = {
            "fig_count": "5",
            "table_count": "3",
            "ref_count": "97",
        }
        self.manuscript.save()
        url = reverse("manuscript_step_front", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {"action": "mark", "source_text": "Hello front text"},
        )
        self.assertRedirects(response, url)
        self.assertEqual(
            mock_resolve.call_args.kwargs["counts"],
            {
                "fig_count": "5",
                "table_count": "3",
                "ref_count": "97",
            },
        )
        self.manuscript.refresh_from_db()
        self.assertIn("<history>", self.manuscript.front_marked_xml)
        self.assertIn('<fig-count count="5"/>', self.manuscript.front_marked_xml)
        self.assertIn('<ref-count count="97"/>', self.manuscript.front_marked_xml)

    def test_api_save_front_persists_history_and_counts(self):
        url = reverse("manuscript_api_save_front", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "marked": {
                        "titles": [
                            {"kind": "main", "text": "Saved title", "language": "en"}
                        ],
                        "history": [
                            {
                                "type": "received",
                                "day": "05",
                                "month": "08",
                                "year": "2025",
                            },
                            {
                                "type": "accepted",
                                "day": "27",
                                "month": "03",
                                "year": "2026",
                            },
                        ],
                        "counts": {
                            "fig_count": "5",
                            "table_count": "3",
                            "ref_count": "97",
                        },
                    }
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.manuscript.refresh_from_db()
        self.assertIn("<history>", self.manuscript.front_marked_xml)
        self.assertIn('date-type="received"', self.manuscript.front_marked_xml)
        self.assertIn("<counts>", self.manuscript.front_marked_xml)
        self.assertIn('<fig-count count="5"/>', self.manuscript.front_marked_xml)

    def test_package_step_renders(self):
        response = self.client.get(
            reverse("manuscript_step_package", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pacote")
        self.assertContains(response, "Build SPS package")
        self.assertContains(response, 'name="include_pdf"')
        self.assertContains(response, 'type="checkbox"')
        self.assertContains(response, "Include PDF generated from the XML")

    def test_completed_steps_use_is_complete(self):
        self.manuscript.status = ManuscriptStatus.BACK
        self.manuscript.save(update_fields=["status"])
        response = self.client.get(
            reverse("manuscript_step_back", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('is-complete">Front</a>', content)
        self.assertIn('is-complete">Body</a>', content)
        self.assertIn('active">Back</a>', content)
        self.assertNotIn('is-complete">Back</a>', content)
        self.assertNotIn('is-complete">Validar</a>', content)
        self.assertNotIn('is-complete">Pacote</a>', content)

    def test_ready_status_marks_validate_complete(self):
        self.manuscript.status = ManuscriptStatus.READY
        self.manuscript.save(update_fields=["status"])
        response = self.client.get(
            reverse("manuscript_step_package", args=[self.manuscript.pk])
        )
        content = response.content.decode()
        self.assertIn('is-complete">Front</a>', content)
        self.assertIn('is-complete">Body</a>', content)
        self.assertIn('is-complete">Back</a>', content)
        self.assertIn('is-complete">Validar</a>', content)
        self.assertIn('active">Pacote</a>', content)
        self.assertNotIn('is-complete">Pacote</a>', content)

    def test_published_status_marks_package_complete(self):
        self.manuscript.status = ManuscriptStatus.PUBLISHED
        self.manuscript.save(update_fields=["status"])
        response = self.client.get(
            reverse("manuscript_step_package", args=[self.manuscript.pk])
        )
        content = response.content.decode()
        self.assertIn('active is-complete">Pacote</a>', content)

    def test_front_step_shows_marked_xml_after_marking(self):
        front_marked_xml = get_front_xml(
            {
                "titles": [
                    {"kind": "main", "text": "Marked front title", "language": "en"}
                ],
            }
        )
        self.manuscript.front_marked_xml = front_marked_xml
        self.manuscript.save(update_fields=["front_marked_xml"])
        response = self.client.get(
            reverse("manuscript_step_front", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('data-manuscript-source-tab="marked"', content)
        self.assertIn('data-manuscript-source-panel="marked"', content)
        self.assertNotIn('type="radio"', content)
        self.assertNotIn('<label for="id_source_text">', content)
        self.assertIn('class="form-control manuscript-xml-preview"', content)
        self.assertIn("Marked front title", content)
        marked_panel = content.split('data-manuscript-source-panel="marked"', 1)[1]
        marked_panel = marked_panel.split("</div>", 1)[0]
        self.assertNotIn("readonly", marked_panel)
        self.assertIn('name="front_marked_xml"', marked_panel)
        self.assertIn('value="save_marked_xml"', marked_panel)

    def test_front_step_shows_tag_statistics_after_marking(self):
        front_marked_xml = get_front_xml(
            {
                "titles": [
                    {"kind": "main", "text": "Marked front title", "language": "en"}
                ],
                "abstracts": [
                    {"kind": "main", "title": "Abstract", "text": "English abstract."}
                ],
                "keywords": [
                    {
                        "language": "en",
                        "title": "Keywords",
                        "keywords": ["Forest birds", "Cerrado"],
                    }
                ],
            }
        )
        self.manuscript.front_marked_xml = front_marked_xml
        self.manuscript.save(update_fields=["front_marked_xml"])
        response = self.client.get(
            reverse("manuscript_step_front", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('data-manuscript-source-tab="stats"', content)
        self.assertIn('data-manuscript-source-panel="stats"', content)
        tabs = content.split('role="tablist"', 1)[1].split("</div>", 1)[0]
        self.assertLess(tabs.find("Marked text"), tabs.find("XML tags"))
        stats_panel = content.split('data-manuscript-source-panel="stats"', 1)[1]
        self.assertIn("<code>kwd</code>", stats_panel)
        self.assertIn("<code>article-title</code>", stats_panel)
        self.assertRegex(stats_panel, r"<code>kwd</code></td>\s*<td>2</td>")
        self.assertRegex(stats_panel, r"<code>article-title</code></td>\s*<td>1</td>")
        expected_total = sum(
            1 for _ in etree.fromstring(front_marked_xml.encode("utf-8")).iter()
        )
        self.assertRegex(stats_panel, rf"<th>Total</th>\s*<th>{expected_total}</th>")

    def test_save_marked_xml_updates_manuscript(self):
        front_marked_xml = get_front_xml(
            {
                "titles": [
                    {"kind": "main", "text": "Original title", "language": "en"}
                ],
            }
        )
        self.manuscript.front_marked_xml = front_marked_xml
        self.manuscript.save(update_fields=["front_marked_xml"])
        updated_xml = get_front_xml(
            {
                "titles": [{"kind": "main", "text": "Edited title", "language": "en"}],
            }
        )
        url = reverse("manuscript_step_front", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {"action": "save_marked_xml", "front_marked_xml": updated_xml},
        )
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        self.assertIn("Edited title", self.manuscript.front_marked_xml)
        self.assertNotIn("Original title", self.manuscript.front_marked_xml)
        self.assertEqual(self.manuscript.assembled_xml, "")

    def test_save_marked_xml_updates_assembled_xml_when_complete(self):
        self.manuscript.body_marked_xml = get_body_xml(
            {
                "sections": [
                    {
                        "title": "Intro",
                        "content": [{"type": "p", "text": "Body paragraph."}],
                        "sections": [],
                    }
                ]
            }
        )
        self.manuscript.save(update_fields=["body_marked_xml"])
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
        updated_xml = get_front_xml(
            {
                "titles": [
                    {"kind": "main", "text": "Assembled edited title", "language": "en"}
                ],
            }
        )
        url = reverse("manuscript_step_front", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {"action": "save_marked_xml", "front_marked_xml": updated_xml},
        )
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        self.assertIn("Assembled edited title", self.manuscript.assembled_xml)
        self.assertIn("Body paragraph.", self.manuscript.assembled_xml)

    def test_save_marked_xml_rejects_invalid_xml(self):
        front_marked_xml = get_front_xml(
            {
                "titles": [
                    {"kind": "main", "text": "Original title", "language": "en"}
                ],
            }
        )
        self.manuscript.front_marked_xml = front_marked_xml
        self.manuscript.save(update_fields=["front_marked_xml"])
        url = reverse("manuscript_step_front", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {"action": "save_marked_xml", "front_marked_xml": "<not-xml>"},
        )
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        self.assertIn("Original title", self.manuscript.front_marked_xml)

    def test_front_step_hides_marked_tab_before_marking(self):
        response = self.client.get(
            reverse("manuscript_step_front", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-manuscript-source-tab="marked"')
        self.assertNotContains(response, 'data-manuscript-source-tab="stats"')
        self.assertNotContains(response, 'class="form-control manuscript-xml-preview"')

    def test_front_approve_button_is_in_floating_footer(self):
        response = self.client.get(
            reverse("manuscript_step_front", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('class="footer"', content)
        self.assertIn('class="footer__container manuscript-wizard__footer"', content)
        footer = content.split('class="footer"', 1)[1]
        self.assertIn("Approve and continue", footer)
        self.assertNotIn(
            "Approve and continue",
            content.split('class="footer"', 1)[0],
        )

    def test_save_source_persists_front_text(self):
        url = reverse("manuscript_step_front", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {"action": "save_source", "source_text": "Title and authors of the paper."},
        )
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        self.assertEqual(
            self.manuscript.front_source_text,
            "Title and authors of the paper.",
        )

    def test_save_source_empty_shows_error(self):
        url = reverse("manuscript_step_front", args=[self.manuscript.pk])
        response = self.client.post(url, {"action": "save_source", "source_text": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Provide front text or a .docx file.")
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.front_source_text, "")

    @patch("manuscript.services.marking.resolve_front_result")
    def test_mark_saves_posted_source_then_marks(self, mock_resolve):
        mock_resolve.return_value = {
            "data": {
                "titles": [{"kind": "main", "text": "Hello", "language": "en"}],
            }
        }
        url = reverse("manuscript_step_front", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {"action": "mark", "source_text": "Hello front text"},
        )
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.front_source_text, "Hello front text")
        self.assertIn("Hello", self.manuscript.front_marked_xml)
        mock_resolve.assert_called_once()
        self.assertEqual(mock_resolve.call_args.args[0], "Hello front text")

    @patch("manuscript.services.marking.resolve_front_result")
    def test_mark_uses_saved_source_when_post_is_empty(self, mock_resolve):
        mock_resolve.return_value = {
            "data": {
                "titles": [{"kind": "main", "text": "Saved title", "language": "en"}],
            }
        }
        self.manuscript.front_source_text = "Already saved front"
        self.manuscript.save(update_fields=["front_source_text"])
        url = reverse("manuscript_step_front", args=[self.manuscript.pk])
        response = self.client.post(url, {"action": "mark", "source_text": ""})
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        self.assertIn("Saved title", self.manuscript.front_marked_xml)
        mock_resolve.assert_called_once()
        self.assertEqual(mock_resolve.call_args.args[0], "Already saved front")

    @patch("manuscript.services.marking.resolve_front_result")
    def test_mark_error_keeps_saved_source_and_shows_message(self, mock_resolve):
        mock_resolve.side_effect = MarkingError("Front Llama returned invalid JSON")
        self.manuscript.front_source_text = "Front that failed to mark"
        self.manuscript.save(update_fields=["front_source_text"])
        url = reverse("manuscript_step_front", args=[self.manuscript.pk])
        response = self.client.post(url, {"action": "mark"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Front Llama returned invalid JSON")
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.front_source_text, "Front that failed to mark")
        self.assertEqual(self.manuscript.front_marked_xml, "")

    def test_body_approve_button_is_in_floating_footer(self):
        self.manuscript.status = ManuscriptStatus.BODY
        self.manuscript.save(update_fields=["status"])
        response = self.client.get(
            reverse("manuscript_step_body", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        footer = response.content.decode().split('class="footer"', 1)[1]
        self.assertIn("Approve and continue", footer)
        self.assertIn("Back to front", footer)

    def test_body_step_shows_marked_xml_after_marking(self):
        body_marked_xml = get_body_xml(
            {
                "sections": [
                    {
                        "title": "Introduction",
                        "content": [{"type": "p", "text": "Marked body paragraph."}],
                        "sections": [],
                    }
                ]
            }
        )
        self.manuscript.status = ManuscriptStatus.BODY
        self.manuscript.body_marked_xml = body_marked_xml
        self.manuscript.save(update_fields=["status", "body_marked_xml"])
        response = self.client.get(
            reverse("manuscript_step_body", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('data-manuscript-source-tab="marked"', content)
        self.assertIn('data-manuscript-source-panel="marked"', content)
        self.assertNotIn('type="radio"', content)
        self.assertNotIn('<label for="id_source_text">', content)
        self.assertIn('class="form-control manuscript-xml-preview"', content)
        self.assertIn("Marked body paragraph.", content)
        marked_panel = content.split('data-manuscript-source-panel="marked"', 1)[1]
        marked_panel = marked_panel.split("</div>", 1)[0]
        self.assertNotIn("readonly", marked_panel)
        self.assertIn('name="body_marked_xml"', marked_panel)
        self.assertIn('value="save_marked_xml"', marked_panel)

    def test_body_save_marked_xml_updates_manuscript(self):
        body_marked_xml = get_body_xml(
            {
                "sections": [
                    {
                        "title": "Intro",
                        "content": [{"type": "p", "text": "Original paragraph."}],
                        "sections": [],
                    }
                ]
            }
        )
        self.manuscript.status = ManuscriptStatus.BODY
        self.manuscript.body_marked_xml = body_marked_xml
        self.manuscript.save(update_fields=["status", "body_marked_xml"])
        updated_xml = get_body_xml(
            {
                "sections": [
                    {
                        "title": "Intro",
                        "content": [{"type": "p", "text": "Edited paragraph."}],
                        "sections": [],
                    }
                ]
            }
        )
        url = reverse("manuscript_step_body", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {"action": "save_marked_xml", "body_marked_xml": updated_xml},
        )
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        self.assertIn("Edited paragraph.", self.manuscript.body_marked_xml)
        self.assertNotIn("Original paragraph.", self.manuscript.body_marked_xml)

    def test_body_save_marked_xml_rejects_invalid_xml(self):
        body_marked_xml = get_body_xml(
            {
                "sections": [
                    {
                        "title": "Intro",
                        "content": [{"type": "p", "text": "Original paragraph."}],
                        "sections": [],
                    }
                ]
            }
        )
        self.manuscript.status = ManuscriptStatus.BODY
        self.manuscript.body_marked_xml = body_marked_xml
        self.manuscript.save(update_fields=["status", "body_marked_xml"])
        url = reverse("manuscript_step_body", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {"action": "save_marked_xml", "body_marked_xml": "<not-xml>"},
        )
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        self.assertIn("Original paragraph.", self.manuscript.body_marked_xml)

    def test_body_step_hides_marked_tab_before_marking(self):
        self.manuscript.status = ManuscriptStatus.BODY
        self.manuscript.save(update_fields=["status"])
        response = self.client.get(
            reverse("manuscript_step_body", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-manuscript-source-tab="marked"')
        self.assertNotContains(response, 'class="form-control manuscript-xml-preview"')
        self.assertContains(response, 'name="images"')
        self.assertContains(response, "multiple")
        self.assertContains(response, 'name="images_zip"')

    def test_body_save_source_persists_multiple_images_and_zip(self):
        self.manuscript.status = ManuscriptStatus.BODY
        self.manuscript.save(update_fields=["status"])
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zipped:
            jpeg = jpeg_upload("fig-3.jpg", color=(0, 0, 255))
            zipped.writestr("fig-3.jpg", jpeg.read())
            zipped.writestr("readme.txt", "ignore")
        archive.seek(0)
        url = reverse("manuscript_step_body", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {
                "action": "save_source",
                "source_text": "Body paragraph mentioning Figure 1.",
                "images": [
                    jpeg_upload("fig-1.jpg", color=(255, 0, 0)),
                    jpeg_upload("fig-2.jpg", color=(0, 255, 0)),
                ],
                "images_zip": SimpleUploadedFile(
                    "figures.zip",
                    archive.getvalue(),
                    content_type="application/zip",
                ),
            },
        )
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        hrefs = list(
            self.manuscript.figure_files.order_by("number").values_list(
                "href", flat=True
            )
        )
        self.assertEqual(hrefs, ["fig-1.jpg", "fig-2.jpg", "fig-3.jpg"])
        listed = self.client.get(url)
        self.assertContains(listed, "fig-1.jpg")
        self.assertContains(listed, "fig-2.jpg")
        self.assertContains(listed, "fig-3.jpg")

    def test_body_save_source_replaces_figure_by_number(self):
        self.manuscript.status = ManuscriptStatus.BODY
        self.manuscript.save(update_fields=["status"])
        url = reverse("manuscript_step_body", args=[self.manuscript.pk])
        self.client.post(
            url,
            {
                "action": "save_source",
                "source_text": "Body paragraph.",
                "images": [jpeg_upload("fig-1.jpg", color=(255, 0, 0))],
            },
        )
        response = self.client.post(
            url,
            {
                "action": "save_source",
                "source_text": "Body paragraph.",
                "images": [jpeg_upload("fig-1.jpg", color=(0, 0, 255))],
            },
        )
        self.assertRedirects(response, url)
        self.assertEqual(self.manuscript.figure_files.count(), 1)
        stored = self.manuscript.figure_files.get()
        self.assertEqual(stored.href, "fig-1.jpg")
        self.assertEqual(stored.number, 1)

    def test_body_save_source_rejects_invalid_image_filename(self):
        self.manuscript.status = ManuscriptStatus.BODY
        self.manuscript.save(update_fields=["status"])
        url = reverse("manuscript_step_body", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {
                "action": "save_source",
                "source_text": "Body paragraph.",
                "images": [jpeg_upload("photo.png")],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid image filename")
        self.assertEqual(self.manuscript.figure_files.count(), 0)

    def test_back_step_shows_marked_xml_after_marking(self):
        marked_xml = (
            '<element-citation publication-type="journal">'
            "<source>Marked journal</source>"
            "</element-citation>"
        )
        self.manuscript.status = ManuscriptStatus.BACK
        self.manuscript.save(update_fields=["status"])
        ManuscriptReference.objects.create(
            manuscript=self.manuscript,
            mixed_citation="Author A. Marked reference.",
            marked={},
            marked_xml=marked_xml,
            sort_order=0,
        )
        response = self.client.get(
            reverse("manuscript_step_back", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('data-manuscript-source-tab="marked"', content)
        self.assertIn('data-manuscript-source-panel="marked"', content)
        self.assertNotIn('type="radio"', content)
        self.assertNotIn('<label for="id_source_text">', content)
        self.assertIn('class="form-control manuscript-xml-preview"', content)
        self.assertIn("Marked journal", content)
        marked_panel = content.split('data-manuscript-source-panel="marked"', 1)[1]
        marked_panel = marked_panel.split("</div>", 1)[0]
        self.assertNotIn("readonly", marked_panel)
        self.assertIn('name="references_marked_xml"', marked_panel)
        self.assertIn('value="save_marked_xml"', marked_panel)

    def test_back_save_marked_xml_updates_manuscript(self):
        original_xml = (
            '<element-citation publication-type="journal">'
            "<source>Original journal</source>"
            "</element-citation>"
        )
        self.manuscript.status = ManuscriptStatus.BACK
        self.manuscript.save(update_fields=["status"])
        ManuscriptReference.objects.create(
            manuscript=self.manuscript,
            mixed_citation="Author A. Original reference.",
            marked={},
            marked_xml=original_xml,
            sort_order=0,
        )
        updated_xml = build_ref_list(
            [
                {
                    "mixed_citation": "Author A. Edited reference.",
                    "data": (
                        '<element-citation publication-type="journal">'
                        "<source>Edited journal</source>"
                        "</element-citation>"
                    ),
                }
            ]
        )
        url = reverse("manuscript_step_back", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {"action": "save_marked_xml", "references_marked_xml": updated_xml},
        )
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        ref = self.manuscript.references.get()
        self.assertEqual(ref.mixed_citation, "Author A. Edited reference.")
        self.assertIn("Edited journal", ref.marked_xml)
        self.assertNotIn("Original journal", ref.marked_xml)

    def test_back_save_marked_xml_rejects_invalid_xml(self):
        original_xml = (
            '<element-citation publication-type="journal">'
            "<source>Original journal</source>"
            "</element-citation>"
        )
        self.manuscript.status = ManuscriptStatus.BACK
        self.manuscript.save(update_fields=["status"])
        ManuscriptReference.objects.create(
            manuscript=self.manuscript,
            mixed_citation="Author A. Original reference.",
            marked={},
            marked_xml=original_xml,
            sort_order=0,
        )
        url = reverse("manuscript_step_back", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {"action": "save_marked_xml", "references_marked_xml": "<not-xml>"},
        )
        self.assertRedirects(response, url)
        ref = self.manuscript.references.get()
        self.assertIn("Original journal", ref.marked_xml)

    def test_back_step_hides_marked_tab_before_marking(self):
        self.manuscript.status = ManuscriptStatus.BACK
        self.manuscript.save(update_fields=["status"])
        response = self.client.get(
            reverse("manuscript_step_back", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-manuscript-source-tab="marked"')
        self.assertNotContains(response, 'class="form-control manuscript-xml-preview"')


class ValidateStepUiTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="validator", email="validator@example.com", password="secret"
        )
        self.client.force_login(user)
        self.manuscript = Manuscript.objects.create(
            title="bn-2025-1828",
            status=ManuscriptStatus.ASSEMBLED,
            creator=user,
            assembled_xml="<article/>",
        )

    def test_validation_groups_render_as_tabs_without_go_to_step(self):
        from wagtail.documents.models import Document

        from xml_manager.models import SPSPackageValidation, SPSPackageValidationStatus

        package = Document(title="bn-2025-1828.zip")
        package.file.save(
            "bn-2025-1828.zip",
            SimpleUploadedFile(
                "bn-2025-1828.zip",
                b"zip",
                content_type="application/zip",
            ),
            save=True,
        )
        csv = Document(title="bn-2025-1828.validation.csv")
        csv.file.save(
            "bn-2025-1828.validation.csv",
            SimpleUploadedFile(
                "bn-2025-1828.validation.csv",
                (
                    b"group,response,item,advice,got_value\n"
                    b"bibliographic strip,ERROR,title,Missing title,\n"
                    b"article languages,WARNING,lang,Check language,en\n"
                    b"reference,CRITICAL,ref,Invalid reference,\n"
                ),
                content_type="text/csv",
            ),
            save=True,
        )
        validation = SPSPackageValidation.objects.create(
            package_document=package,
            validation_document=csv,
            status=SPSPackageValidationStatus.DONE,
            zip_size_bytes=3,
        )
        self.manuscript.sps_package = package
        self.manuscript.validation = validation
        self.manuscript.save(update_fields=["sps_package", "validation", "updated"])

        response = self.client.get(
            reverse("manuscript_step_validate", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("data-manuscript-validation-tabs", content)
        self.assertIn('data-manuscript-validation-tab="CRITICAL"', content)
        self.assertIn('data-manuscript-validation-tab="ERROR"', content)
        self.assertIn('data-manuscript-validation-tab="WARNING"', content)
        self.assertNotIn('data-manuscript-validation-tab="front"', content)
        self.assertIn("bibliographic strip", content)
        self.assertIn("Invalid reference", content)
        self.assertNotIn('name="action" value="open_step"', content)
        self.assertNotContains(response, "Go to step")

    def test_missing_validation_csv_shows_rerun_message(self):
        from wagtail.documents.models import Document

        from xml_manager.models import SPSPackageValidation, SPSPackageValidationStatus

        package = Document(title="bn-2025-1834.zip")
        package.file.save(
            "bn-2025-1834.zip",
            SimpleUploadedFile(
                "bn-2025-1834.zip",
                b"zip",
                content_type="application/zip",
            ),
            save=True,
        )
        csv = Document(title="bn-2025-1834.validation.csv")
        csv.file.save(
            "bn-2025-1834.validation.csv",
            SimpleUploadedFile(
                "bn-2025-1834.validation.csv",
                b"group,response,item,advice,got_value\n",
                content_type="text/csv",
            ),
            save=True,
        )
        csv.file.storage.delete(csv.file.name)
        validation = SPSPackageValidation.objects.create(
            package_document=package,
            validation_document=csv,
            status=SPSPackageValidationStatus.DONE,
            zip_size_bytes=3,
        )
        self.manuscript.sps_package = package
        self.manuscript.validation = validation
        self.manuscript.save(update_fields=["sps_package", "validation", "updated"])

        response = self.client.get(
            reverse("manuscript_step_validate", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "validation report file is missing")
        self.assertNotContains(response, "data-manuscript-validation-tabs")

    def test_assembled_xml_is_editable_and_has_save_button(self):
        response = self.client.get(
            reverse("manuscript_step_validate", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        xml_form = content.split('id="manuscript-assembled-xml-form"', 1)[1]
        xml_form = xml_form.split("</form>", 1)[0]
        self.assertNotIn("readonly", xml_form)
        self.assertIn('name="assembled_xml"', xml_form)
        self.assertIn('value="save_assembled_xml"', xml_form)
        self.assertIn("&lt;article/&gt;", xml_form)

    def test_save_assembled_xml_updates_manuscript(self):
        url = reverse("manuscript_step_validate", args=[self.manuscript.pk])
        updated_xml = "<article><title>Edited assembled title</title></article>"
        response = self.client.post(
            url,
            {"action": "save_assembled_xml", "assembled_xml": updated_xml},
        )
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.assembled_xml, updated_xml)

    def test_save_assembled_xml_rejects_invalid_xml(self):
        url = reverse("manuscript_step_validate", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {"action": "save_assembled_xml", "assembled_xml": "<not-xml>"},
        )
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.assembled_xml, "<article/>")

    def test_save_assembled_xml_accepts_doctype(self):
        url = reverse("manuscript_step_validate", args=[self.manuscript.pk])
        updated_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal '
            'Publishing DTD v1.1 20151215//EN" '
            '"https://jats.nlm.nih.gov/publishing/1.1/JATS-journalpublishing1.dtd">\n'
            "<article><title>With doctype</title></article>"
        )
        response = self.client.post(
            url,
            {"action": "save_assembled_xml", "assembled_xml": updated_xml},
        )
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.assembled_xml, updated_xml)

    def test_validate_saves_assembled_xml_before_revalidation(self):
        url = reverse("manuscript_step_validate", args=[self.manuscript.pk])
        updated_xml = "<article><title>Revalidated title</title></article>"
        with patch(
            "xml_manager.services.utils.validate_zip",
            return_value=([], []),
        ):
            response = self.client.post(
                url,
                {"action": "validate", "assembled_xml": updated_xml},
            )
        self.assertRedirects(response, url)
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.assembled_xml, updated_xml)
        with self.manuscript.sps_package.file.open("rb") as fh:
            with zipfile.ZipFile(fh) as archive:
                xml_names = [
                    name for name in archive.namelist() if name.endswith(".xml")
                ]
                self.assertEqual(len(xml_names), 1)
                self.assertIn(
                    "Revalidated title",
                    archive.read(xml_names[0]).decode("utf-8"),
                )


class PackagePdfBuildTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="pkgpdf", email="pkgpdf@example.com", password="secret"
        )
        self.client.force_login(user)
        self.manuscript = Manuscript.objects.create(
            title="Package pdf",
            status=ManuscriptStatus.READY,
            creator=user,
            assembled_xml="<article><title>Package pdf</title></article>",
        )

    def test_package_build_without_checkbox_skips_pdf(self):
        url = reverse("manuscript_step_package", args=[self.manuscript.pk])
        with patch("manuscript.views.build_sps_zip") as mock_build:
            mock_build.return_value = self.manuscript.sps_package
            response = self.client.post(url, {"action": "build"})
        self.assertRedirects(response, url)
        mock_build.assert_called_once_with(self.manuscript, include_pdf=False)

    def test_package_build_with_checkbox_requests_pdf(self):
        url = reverse("manuscript_step_package", args=[self.manuscript.pk])
        with patch("manuscript.views.build_sps_zip") as mock_build:
            mock_build.return_value = self.manuscript.sps_package
            response = self.client.post(url, {"action": "build", "include_pdf": "on"})
        self.assertRedirects(response, url)
        mock_build.assert_called_once_with(self.manuscript, include_pdf=True)

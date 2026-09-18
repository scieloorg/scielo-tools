from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override

from body.data_utils import get_body_xml
from body.images import attach_figure_hrefs
from front.data_utils import get_front_xml
from manuscript.models import (
    Manuscript,
    ManuscriptFigureFile,
    ManuscriptReference,
    ManuscriptStatus,
)
from manuscript.preview import (
    ManuscriptPreviewError,
    figure_urls_for_manuscript,
    render_article_preview,
    render_article_preview_packtools,
    render_body_preview,
    render_front_preview,
)
from manuscript.services.assembly import assemble_manuscript_xml
from manuscript.services.marking import save_front_marked

User = get_user_model()


class PreviewTests(TestCase):
    def test_render_front_preview_contains_title(self):
        xml = get_front_xml(
            {
                "titles": [{"kind": "main", "text": "Preview title", "language": "en"}],
            }
        )
        html = render_front_preview(xml)
        self.assertIn("Preview title", html)
        self.assertIn("article-title", html)

    def test_render_front_preview_uses_xml_labels_not_ui_translation(self):
        xml = get_front_xml(
            {
                "titles": [{"kind": "main", "text": "Preview title", "language": "en"}],
                "abstracts": [
                    {"kind": "main", "title": "Abstract", "text": "English abstract."},
                    {
                        "kind": "translated",
                        "language": "pt",
                        "title": "Resumo",
                        "text": "Resumo em português.",
                    },
                ],
                "keywords": [
                    {
                        "language": "en",
                        "title": "Keywords",
                        "keywords": ["Forest birds"],
                    },
                    {
                        "language": "pt",
                        "title": "Palavras-chave",
                        "keywords": ["Aves florestais"],
                    },
                ],
            }
        )
        with override("pt-br"):
            html = render_front_preview(xml)
        self.assertIn("articleSectionTitle'>Abstract</h2>", html)
        self.assertIn("articleSectionTitle'>Resumo</h2>", html)
        self.assertEqual(html.count("articleSectionTitle'>Resumo</h2>"), 1)
        self.assertIn("<strong>Keywords</strong>", html)
        self.assertIn("<strong>Palavras-chave</strong>", html)
        abstract_pos = html.find("articleSectionTitle'>Abstract</h2>")
        keywords_pos = html.find("<strong>Keywords</strong>")
        resumo_pos = html.find("articleSectionTitle'>Resumo</h2>")
        palavras_pos = html.find("<strong>Palavras-chave</strong>")
        self.assertLess(abstract_pos, keywords_pos)
        self.assertLess(keywords_pos, resumo_pos)
        self.assertLess(resumo_pos, palavras_pos)

    def test_render_front_preview_pairs_keywords_by_language_not_xml_order(self):
        xml = get_front_xml(
            {
                "titles": [{"kind": "main", "text": "Preview title", "language": "en"}],
                "abstracts": [
                    {"kind": "main", "title": "Abstract", "text": "English abstract."},
                    {
                        "kind": "translated",
                        "language": "pt",
                        "title": "Resumo",
                        "text": "Resumo em português.",
                    },
                ],
                "keywords": [
                    {
                        "language": "pt",
                        "title": "Palavras-chave",
                        "keywords": ["Aves florestais"],
                    },
                    {
                        "language": "en",
                        "title": "Keywords",
                        "keywords": ["Forest birds"],
                    },
                ],
            }
        )
        html = render_front_preview(xml)
        abstract_pos = html.find("articleSectionTitle'>Abstract</h2>")
        keywords_pos = html.find("<strong>Keywords</strong>")
        resumo_pos = html.find("articleSectionTitle'>Resumo</h2>")
        palavras_pos = html.find("<strong>Palavras-chave</strong>")
        self.assertLess(abstract_pos, keywords_pos)
        self.assertLess(keywords_pos, resumo_pos)
        self.assertLess(resumo_pos, palavras_pos)
        english_block = html[abstract_pos:resumo_pos]
        self.assertIn("Forest birds", english_block)
        self.assertNotIn("Aves florestais", english_block)
        portuguese_block = html[resumo_pos:]
        self.assertIn("Aves florestais", portuguese_block)
        self.assertNotIn("Forest birds", portuguese_block)

    def test_render_front_preview_contains_history_and_counts(self):
        xml = get_front_xml(
            {
                "titles": [{"kind": "main", "text": "Preview title", "language": "en"}],
                "history": [
                    {"type": "received", "day": "05", "month": "08", "year": "2025"},
                    {"type": "accepted", "day": "27", "month": "03", "year": "2026"},
                ],
                "counts": {
                    "fig_count": "5",
                    "table_count": "3",
                    "ref_count": "97",
                },
            }
        )
        html = render_front_preview(xml)
        self.assertIn("articleTimeline", html)
        self.assertIn("articleSectionTitle'>History</h2>", html)
        self.assertIn("articleSectionTitle'>Counts</h2>", html)
        self.assertIn("<strong>Received</strong>", html)
        self.assertIn("05 August 2025", html)
        self.assertIn("<strong>Accepted</strong>", html)
        self.assertIn("27 March 2026", html)
        self.assertIn("<strong>Figures</strong>", html)
        self.assertIn("<strong>Tables</strong>", html)
        self.assertIn("<strong>References</strong>", html)
        self.assertIn(">5</li>", html)
        self.assertIn(">3</li>", html)
        self.assertIn(">97</li>", html)
        self.assertNotIn("fig-count", html)
        self.assertNotIn("received:", html)
        self.assertNotIn("05/08/2025", html)

    def test_render_front_preview_localizes_history_months(self):
        xml = get_front_xml(
            {
                "titles": [{"kind": "main", "text": "Preview title", "language": "en"}],
                "history": [
                    {"type": "received", "day": "05", "month": "08", "year": "2025"},
                    {"type": "rev-recd", "day": "10", "month": "09", "year": "2025"},
                    {"type": "accepted", "day": "27", "month": "03", "year": "2026"},
                ],
                "counts": {
                    "fig_count": "5",
                    "table_count": "3",
                    "equation_count": "0",
                    "ref_count": "97",
                },
            }
        )
        with override("pt-br"):
            html = render_front_preview(xml)
        self.assertIn("articleTimeline", html)
        self.assertIn("05 Agosto 2025", html)
        self.assertIn("10 Setembro 2025", html)
        self.assertIn("27 Março 2026", html)
        self.assertIn(">0</li>", html)
        self.assertNotIn("fig-count", html)
        self.assertNotIn("equation-count", html)

    def test_render_body_preview_contains_tables_in_document_order(self):
        xml = get_body_xml(
            {
                "sections": [
                    {
                        "title": "Methods",
                        "content": [
                            {"type": "p", "text": "Before table."},
                            {
                                "type": "table-wrap",
                                "id": "t1",
                                "label": "Table 1",
                                "caption": "Sample data",
                                "headers": ["A", "B"],
                                "rows": [["1", "2"]],
                                "footnotes": ["Note about A."],
                            },
                            {"type": "p", "text": "After table."},
                            {
                                "type": "fig",
                                "label": "Figure 1",
                                "caption": "A chart.",
                            },
                        ],
                        "sections": [],
                    }
                ]
            }
        )
        html = render_body_preview(xml)
        self.assertIn("Table 1", html)
        self.assertIn("Sample data", html)
        self.assertIn("<th>A</th>", html)
        self.assertIn("<th>B</th>", html)
        self.assertIn("<td>1</td>", html)
        self.assertIn("<td>2</td>", html)
        self.assertIn("table-hover", html)
        self.assertIn("Note about A.", html)
        self.assertIn("Figure 1", html)
        self.assertLess(html.find("Before table."), html.find("Table 1"))
        self.assertLess(html.find("Table 1"), html.find("After table."))
        self.assertLess(html.find("After table."), html.find("Figure 1"))

    def test_render_body_preview_shows_figure_image_when_url_provided(self):
        marked = {
            "sections": [
                {
                    "title": "Results",
                    "content": [
                        {
                            "type": "fig",
                            "id": "f1",
                            "label": "Figure 1",
                            "caption": "Sample chart.",
                        }
                    ],
                    "sections": [],
                }
            ]
        }
        attach_figure_hrefs(marked, {"1": "fig-1.jpg"})
        xml = get_body_xml(marked)
        html = render_body_preview(
            xml,
            figure_urls={"fig-1.jpg": "/media/manuscript/figures/2026/09/fig-1.jpg"},
        )
        self.assertIn('class="graphic"', html)
        self.assertIn('src="/media/manuscript/figures/2026/09/fig-1.jpg"', html)
        self.assertIn("Figure 1", html)
        self.assertIn("Sample chart.", html)

    def test_render_body_preview_omits_image_without_matching_url(self):
        marked = {
            "sections": [
                {
                    "title": "Results",
                    "content": [
                        {
                            "type": "fig",
                            "id": "f1",
                            "label": "Figure 1",
                            "caption": "Sample chart.",
                        }
                    ],
                    "sections": [],
                }
            ]
        }
        attach_figure_hrefs(marked, {"1": "fig-1.jpg"})
        xml = get_body_xml(marked)
        html = render_body_preview(xml)
        self.assertNotIn("<img", html)
        self.assertIn("Figure 1", html)

    def test_preview_part_body_shows_uploaded_figure_image(self):
        user = User.objects.create_superuser(
            username="bodyfig", email="bodyfig@example.com", password="secret"
        )
        marked = {
            "sections": [
                {
                    "title": "Results",
                    "content": [
                        {
                            "type": "fig",
                            "id": "f1",
                            "label": "Figure 1",
                            "caption": "Preview figure.",
                        }
                    ],
                    "sections": [],
                }
            ]
        }
        attach_figure_hrefs(marked, {"1": "fig-1.jpg"})
        manuscript = Manuscript.objects.create(
            title="Body figure preview",
            status=ManuscriptStatus.BODY,
            creator=user,
            body_marked_xml=get_body_xml(marked),
        )
        figure = ManuscriptFigureFile(
            manuscript=manuscript,
            number=1,
            href="fig-1.jpg",
            original_name="fig-1.jpg",
            sort_order=1,
        )
        figure.file.save("fig-1.jpg", ContentFile(b"jpeg-preview"), save=True)
        self.client.force_login(user)
        response = self.client.get(
            reverse("manuscript_preview_part", args=[manuscript.pk, "body"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="graphic"')
        self.assertContains(response, figure.file.url)
        self.assertContains(response, "Preview figure.")

    def test_render_article_preview_shows_figure_image(self):
        user = User.objects.create_superuser(
            username="articlefig", email="articlefig@example.com", password="secret"
        )
        manuscript = self._assembled_manuscript(user)
        marked = {
            "sections": [
                {
                    "title": "Intro",
                    "content": [
                        {
                            "type": "fig",
                            "id": "f1",
                            "label": "Figure 1",
                            "caption": "Article figure.",
                        }
                    ],
                    "sections": [],
                }
            ]
        }
        attach_figure_hrefs(marked, {"1": "fig-1.jpg"})
        manuscript.body_marked_xml = get_body_xml(marked)
        manuscript.save(update_fields=["body_marked_xml"])
        figure = ManuscriptFigureFile(
            manuscript=manuscript,
            number=1,
            href="fig-1.jpg",
            original_name="fig-1.jpg",
            sort_order=1,
        )
        figure.file.save("fig-1.jpg", ContentFile(b"jpeg-article"), save=True)
        assemble_manuscript_xml(manuscript)
        manuscript.refresh_from_db()
        html = render_article_preview(
            manuscript.assembled_xml,
            figure_urls=figure_urls_for_manuscript(manuscript),
        )
        self.assertIn(figure.file.url, html)
        self.assertIn("Article figure.", html)

    def test_preview_part_renders_design_system_frame(self):
        user = User.objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        manuscript = Manuscript.objects.create(
            title="Preview article",
            status=ManuscriptStatus.FRONT,
            creator=user,
            front_marked_xml=get_front_xml(
                {
                    "titles": [
                        {"kind": "main", "text": "Preview title", "language": "en"}
                    ],
                }
            ),
        )
        self.client.force_login(user)
        response = self.client.get(
            reverse("manuscript_preview_part", args=[manuscript.pk, "front"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "vendor/scielo-ds/css/bootstrap.css")
        self.assertContains(response, "vendor/scielo-ds/css/article.css")
        self.assertContains(response, "manuscript/css/preview.css")
        self.assertContains(response, "article-title")
        self.assertContains(response, "Preview title")

    def _assembled_manuscript(self, user):
        manuscript = Manuscript.objects.create(
            title="Packtools preview",
            status=ManuscriptStatus.ASSEMBLED,
            creator=user,
            language="en",
            front_marked_xml=get_front_xml(
                {
                    "titles": [
                        {"kind": "main", "text": "Packtools title", "language": "en"}
                    ],
                }
            ),
            body_marked_xml=get_body_xml(
                {
                    "sections": [
                        {
                            "title": "Intro",
                            "content": [{"type": "p", "text": "Packtools paragraph."}],
                            "sections": [],
                        }
                    ]
                }
            ),
        )
        ManuscriptReference.objects.create(
            manuscript=manuscript,
            mixed_citation="Author A. Article.",
            marked={"reftype": "journal", "source": "Journal", "date": "2024"},
            marked_xml=(
                '<element-citation publication-type="journal">'
                "<source>Journal</source><year>2024</year>"
                "</element-citation>"
            ),
            sort_order=0,
        )
        assemble_manuscript_xml(manuscript)
        manuscript.refresh_from_db()
        return manuscript

    def test_render_article_preview_packtools_contains_article_content(self):
        user = User.objects.create_superuser(
            username="packtools", email="packtools@example.com", password="secret"
        )
        manuscript = self._assembled_manuscript(user)
        html = render_article_preview_packtools(
            manuscript.assembled_xml,
            language=manuscript.language,
        )
        self.assertIn("Packtools title", html)
        self.assertIn("Packtools paragraph.", html)
        self.assertIn("article-title", html)

    def test_render_article_preview_packtools_raises_on_empty_xml(self):
        with self.assertRaises(ManuscriptPreviewError):
            render_article_preview_packtools("", language="en")

    @patch("manuscript.preview.HTMLGenerator.parse")
    def test_preview_part_falls_back_when_packtools_fails(self, mock_parse):
        user = User.objects.create_superuser(
            username="fallback", email="fallback@example.com", password="secret"
        )
        manuscript = self._assembled_manuscript(user)
        mock_parse.side_effect = RuntimeError("packtools unavailable")
        self.client.force_login(user)
        url = reverse("manuscript_preview_part", args=[manuscript.pk, "article"])
        response = self.client.get(f"{url}?renderer=packtools")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Packtools title")
        fallback_html = render_article_preview(manuscript.assembled_xml)
        self.assertIn("Packtools title", fallback_html)

    def test_preview_part_uses_manual_renderer_without_query_param(self):
        user = User.objects.create_superuser(
            username="manual", email="manual@example.com", password="secret"
        )
        manuscript = self._assembled_manuscript(user)
        self.client.force_login(user)
        url = reverse("manuscript_preview_part", args=[manuscript.pk, "article"])
        with patch(
            "manuscript.views.render_article_preview_packtools"
        ) as mock_packtools:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        mock_packtools.assert_not_called()
        self.assertContains(response, "Packtools title")

    def test_validate_step_preview_iframe_uses_packtools_renderer(self):
        user = User.objects.create_superuser(
            username="validate", email="validate@example.com", password="secret"
        )
        manuscript = self._assembled_manuscript(user)
        self.client.force_login(user)
        response = self.client.get(
            reverse("manuscript_step_validate", args=[manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "renderer=packtools")

    def test_article_preview_reflects_front_edit(self):
        user = User.objects.create_superuser(
            username="reassemble",
            email="reassemble@example.com",
            password="secret",
        )
        manuscript = self._assembled_manuscript(user)
        save_front_marked(
            manuscript,
            {
                "titles": [
                    {"kind": "main", "text": "Edited preview title", "language": "en"}
                ]
            },
            user=user,
        )
        self.client.force_login(user)
        response = self.client.get(
            reverse("manuscript_preview_part", args=[manuscript.pk, "article"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edited preview title")
        self.assertNotContains(response, "Packtools title")

    def test_package_step_preview_iframe_uses_packtools_renderer(self):
        user = User.objects.create_superuser(
            username="package", email="package@example.com", password="secret"
        )
        manuscript = self._assembled_manuscript(user)
        manuscript.status = ManuscriptStatus.READY
        manuscript.save(update_fields=["status"])
        self.client.force_login(user)
        response = self.client.get(
            reverse("manuscript_step_package", args=[manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "renderer=packtools")

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from wagtail.documents.models import Document
from wagtail.models import Collection

from front.tests.test_docx import make_docx_bytes
from manuscript.models import (
    Manuscript,
    ManuscriptMarkingPart,
    ManuscriptMarkingRun,
    ManuscriptMarkingRunStatus,
    ManuscriptStatus,
)


class ManuscriptListDisplayTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)
        self.list_url = reverse("wagtailsnippets_manuscript_manuscript:list")

    def test_list_headers_include_status_file_type_and_language(self):
        Manuscript.objects.create(title="Cabeçalhos")
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Status")
        self.assertContains(response, "Source DOCX")
        self.assertContains(response, "Article type")
        self.assertContains(response, "Original language")

    def test_list_row_shows_status_file_link_article_type_and_language(self):
        upload = SimpleUploadedFile(
            "sample.docx",
            b"docx",
            content_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        )
        document = Document(title="sample.docx")
        document.file.save("sample.docx", upload, save=True)
        manuscript = Manuscript.objects.create(
            title="Lista de manuscritos",
            status=ManuscriptStatus.FRONT,
            source_document=document,
            article_type="review-article",
            language="es",
        )

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, manuscript.title)
        self.assertContains(response, manuscript.get_status_display())
        self.assertContains(response, "sample.docx")
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, document.url)
        self.assertContains(response, "Revisão de literatura (review-article)")
        self.assertContains(response, "Español (es)")

    def test_list_row_without_source_document_shows_dash(self):
        Manuscript.objects.create(
            title="Sem arquivo",
            article_type="research-article",
            language="pt",
        )
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sem arquivo")
        self.assertContains(response, "-")
        self.assertContains(response, "Artigo original (research-article)")
        self.assertContains(response, "Português (pt)")


class ManuscriptCreateIntakeTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="creator", email="creator@example.com", password="secret"
        )
        self.client.force_login(user)

    @patch("body.tasks.mark_body_text.apply_async")
    @patch("front.tasks.mark_front_text.apply_async")
    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_create_from_docx_persists_front_counts_and_enqueues_back_first(
        self, mock_back, mock_front, mock_body
    ):
        back_result = MagicMock()
        back_result.id = "task-back-1"
        mock_back.return_value = back_result
        upload = SimpleUploadedFile(
            "article.docx",
            make_docx_bytes(
                [
                    "Título de teste",
                    "Ana Silva",
                    "Received: 05/08/2025",
                    "Accepted: 27/03/2026",
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
        response = self.client.post(
            reverse("wagtailsnippets_manuscript_manuscript:add"),
            {
                "title": "From docx",
                "article_type": "research-article",
                "language": "en",
                "specific_use": "sps-1.10",
                "source_docx": upload,
            },
        )
        self.assertEqual(response.status_code, 302)
        manuscript = Manuscript.objects.get(title="From docx")
        self.assertRedirects(
            response,
            reverse("manuscript_step_front", args=[manuscript.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(manuscript.front_counts.get("fig_count"), "2")
        self.assertEqual(manuscript.front_counts.get("table_count"), "1")
        self.assertEqual(manuscript.front_counts.get("ref_count"), "2")
        self.assertIn("Received: 05/08/2025", manuscript.front_source_text)
        self.assertIn("Accepted: 27/03/2026", manuscript.front_source_text)
        mock_back.assert_called_once()
        mock_front.assert_not_called()
        mock_body.assert_not_called()
        runs = {
            run.part: run
            for run in ManuscriptMarkingRun.objects.filter(manuscript=manuscript)
        }
        self.assertEqual(
            runs[ManuscriptMarkingPart.BACK].status,
            ManuscriptMarkingRunStatus.PENDING,
        )
        self.assertEqual(runs[ManuscriptMarkingPart.BACK].task_id, "task-back-1")
        self.assertEqual(
            runs[ManuscriptMarkingPart.FRONT].status,
            ManuscriptMarkingRunStatus.PENDING,
        )
        self.assertEqual(runs[ManuscriptMarkingPart.FRONT].task_id, "")
        self.assertEqual(
            runs[ManuscriptMarkingPart.BODY].status,
            ManuscriptMarkingRunStatus.PENDING,
        )
        self.assertEqual(runs[ManuscriptMarkingPart.BODY].task_id, "")

    @patch("body.tasks.mark_body_text.apply_async")
    @patch("front.tasks.mark_front_text.apply_async")
    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_create_from_docx_uses_filename_collection(
        self, mock_back, mock_front, mock_body
    ):
        mock_back.return_value = MagicMock(id="task-back")
        upload = SimpleUploadedFile(
            "bn-2025-1834.docx",
            make_docx_bytes(
                [
                    "Título de teste",
                    "Ana Silva",
                    "Introduction",
                    "Corpo do artigo",
                    "References",
                    "Smith J. A paper. 2020.",
                ]
            ),
            content_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        )
        response = self.client.post(
            reverse("wagtailsnippets_manuscript_manuscript:add"),
            {
                "title": "From package docx",
                "article_type": "research-article",
                "language": "en",
                "specific_use": "sps-1.10",
                "source_docx": upload,
            },
        )
        self.assertEqual(response.status_code, 302)
        manuscript = Manuscript.objects.get(title="From package docx")
        self.assertEqual(manuscript.source_document.collection.name, "bn-2025-1834")

    @patch("body.tasks.mark_body_text.apply_async")
    @patch("front.tasks.mark_front_text.apply_async")
    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_create_from_docx_reuses_collection_for_same_filename(
        self, mock_back, mock_front, mock_body
    ):
        mock_back.return_value = MagicMock(id="task-back")
        payload = make_docx_bytes(
            [
                "Título de teste",
                "Ana Silva",
                "Introduction",
                "Corpo do artigo",
                "References",
                "Smith J. A paper. 2020.",
            ]
        )
        content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        first = self.client.post(
            reverse("wagtailsnippets_manuscript_manuscript:add"),
            {
                "title": "First package docx",
                "article_type": "research-article",
                "language": "en",
                "specific_use": "sps-1.10",
                "source_docx": SimpleUploadedFile(
                    "bn-2025-1834.docx",
                    payload,
                    content_type=content_type,
                ),
            },
        )
        self.assertEqual(first.status_code, 302)
        first_collection_id = Manuscript.objects.get(
            title="First package docx"
        ).source_document.collection_id
        second = self.client.post(
            reverse("wagtailsnippets_manuscript_manuscript:add"),
            {
                "title": "Second package docx",
                "article_type": "research-article",
                "language": "en",
                "specific_use": "sps-1.10",
                "source_docx": SimpleUploadedFile(
                    "bn-2025-1834.docx",
                    payload,
                    content_type=content_type,
                ),
            },
        )
        self.assertEqual(second.status_code, 302)
        second_manuscript = Manuscript.objects.get(title="Second package docx")
        self.assertEqual(
            second_manuscript.source_document.collection_id, first_collection_id
        )
        self.assertEqual(
            Collection.objects.filter(name="bn-2025-1834").count(),
            1,
        )

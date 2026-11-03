import hashlib
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from wagtail.documents.models import Document
from wagtail.models import Collection

from front.tests.test_docx import make_docx_bytes
from manuscript.models import (
    Manuscript,
    ManuscriptMarkingPart,
    ManuscriptMarkingRun,
    ManuscriptMarkingRunStatus,
    ManuscriptReference,
    ManuscriptStatus,
)
from manuscript.tests.helpers import attach_manuscript_figure


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
        self.assertContains(response, "Progress")
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

    def test_list_row_shows_overall_progress_percentage_for_each_package(self):
        draft = Manuscript.objects.create(
            title="Pacote inicial",
            front_source_text="Front",
            body_source_text="Body",
            references_source_text="Ref 1",
        )
        partial = Manuscript.objects.create(
            title="Pacote em andamento",
            front_source_text="Front",
            body_source_text="Body",
            references_source_text="Ref 1",
        )
        for part in (
            ManuscriptMarkingPart.BACK,
            ManuscriptMarkingPart.FRONT,
            ManuscriptMarkingPart.BODY,
        ):
            ManuscriptMarkingRun.objects.create(
                manuscript=partial,
                part=part,
                status=ManuscriptMarkingRunStatus.DONE,
            )
        ManuscriptMarkingRun.objects.create(
            manuscript=partial,
            part=ManuscriptMarkingPart.VALIDATE,
            status=ManuscriptMarkingRunStatus.PENDING,
        )
        done_pkg = Manuscript.objects.create(
            title="Pacote completo",
            front_source_text="Front",
            body_source_text="Body",
            references_source_text="Ref 1",
        )
        for part in (
            ManuscriptMarkingPart.BACK,
            ManuscriptMarkingPart.FRONT,
            ManuscriptMarkingPart.BODY,
            ManuscriptMarkingPart.VALIDATE,
            ManuscriptMarkingPart.PDF,
            ManuscriptMarkingPart.HTML,
            ManuscriptMarkingPart.PACKAGE,
        ):
            ManuscriptMarkingRun.objects.create(
                manuscript=done_pkg,
                part=part,
                status=ManuscriptMarkingRunStatus.DONE,
            )

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(f'data-manuscript-list-progress="{draft.pk}"', content)
        self.assertIn(f'data-manuscript-list-progress="{partial.pk}"', content)
        self.assertIn(f'data-manuscript-list-progress="{done_pkg.pk}"', content)
        self.assertIn(">0%</span>", content)
        self.assertIn(">60%</span>", content)
        self.assertIn(">100%</span>", content)
        self.assertIn(
            reverse("manuscript_api_marking_status", args=[partial.pk]),
            content,
        )


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
        content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        first_payload = make_docx_bytes(
            [
                "Título de teste",
                "Ana Silva",
                "Introduction",
                "Corpo do artigo",
                "References",
                "Smith J. A paper. 2020.",
            ]
        )
        second_payload = make_docx_bytes(
            [
                "Título de teste",
                "Ana Silva",
                "Introduction",
                "Outro corpo do artigo",
                "References",
                "Smith J. A paper. 2020.",
            ]
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
                    first_payload,
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
                    second_payload,
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

    @patch("manuscript.services.intake.revoke_task_ids")
    @patch("body.tasks.mark_body_text.apply_async")
    @patch("front.tasks.mark_front_text.apply_async")
    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_create_from_docx_remarks_same_bytes(
        self, mock_back, mock_front, mock_body, mock_revoke
    ):
        mock_back.side_effect = [
            MagicMock(id="task-back-1"),
            MagicMock(id="task-back-2"),
        ]
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
        add_url = reverse("wagtailsnippets_manuscript_manuscript:add")
        first = self.client.post(
            add_url,
            {
                "title": "Original title",
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
        manuscript = Manuscript.objects.get()
        original_pk = manuscript.pk
        creator = manuscript.creator
        other = get_user_model().objects.create_superuser(
            username="other-creator",
            email="other@example.com",
            password="secret",
        )
        manuscript.creator = other
        manuscript.front_marked = {"titles": [{"text": "Old"}]}
        manuscript.front_marked_xml = "<front/>"
        manuscript.assembled_xml = "<article/>"
        manuscript.front_approved_at = timezone.now()
        pdf = Document(title="old.pdf")
        pdf.file.save(
            "old.pdf",
            SimpleUploadedFile("old.pdf", b"%PDF-1.4", content_type="application/pdf"),
            save=True,
        )
        manuscript.generated_pdf = pdf
        manuscript.save()
        ManuscriptReference.objects.create(
            manuscript=manuscript,
            mixed_citation="Smith J. A paper. 2020.",
            sort_order=0,
        )
        figure = attach_manuscript_figure(manuscript)
        second = self.client.post(
            add_url,
            {
                "title": "Retitled package",
                "article_type": "review-article",
                "language": "es",
                "specific_use": "sps-1.10",
                "source_docx": SimpleUploadedFile(
                    "bn-2025-1834.docx",
                    payload,
                    content_type=content_type,
                ),
            },
        )
        self.assertEqual(second.status_code, 302)
        self.assertEqual(Manuscript.objects.count(), 1)
        manuscript.refresh_from_db()
        self.assertEqual(manuscript.pk, original_pk)
        self.assertEqual(manuscript.title, "Retitled package")
        self.assertEqual(manuscript.language, "es")
        self.assertEqual(manuscript.article_type, "review-article")
        self.assertEqual(manuscript.creator_id, other.pk)
        self.assertNotEqual(manuscript.creator_id, creator.pk)
        self.assertEqual(manuscript.source_sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(manuscript.front_marked, {})
        self.assertEqual(manuscript.front_marked_xml, "")
        self.assertEqual(manuscript.assembled_xml, "")
        self.assertIsNone(manuscript.front_approved_at)
        self.assertIsNone(manuscript.generated_pdf_id)
        self.assertFalse(Document.objects.filter(pk=pdf.pk).exists())
        self.assertFalse(manuscript.references.exists())
        self.assertTrue(manuscript.figure_files.filter(pk=figure.pk).exists())
        self.assertEqual(mock_back.call_count, 2)
        self.assertEqual(
            ManuscriptMarkingRun.objects.get(
                manuscript=manuscript, part=ManuscriptMarkingPart.BACK
            ).task_id,
            "task-back-2",
        )
        revoked = mock_revoke.call_args.args[0]
        self.assertIn("task-back-1", revoked)
        self.assertIn(
            "re-marked",
            " ".join(str(message) for message in get_messages(second.wsgi_request)),
        )

    @patch("body.tasks.mark_body_text.apply_async")
    @patch("front.tasks.mark_front_text.apply_async")
    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_create_from_docx_different_bytes_same_filename_creates_another(
        self, mock_back, mock_front, mock_body
    ):
        mock_back.return_value = MagicMock(id="task-back")
        content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        add_url = reverse("wagtailsnippets_manuscript_manuscript:add")
        first_payload = make_docx_bytes(
            [
                "Título de teste",
                "Ana Silva",
                "Introduction",
                "Corpo do artigo",
                "References",
                "Smith J. A paper. 2020.",
            ]
        )
        second_payload = make_docx_bytes(
            [
                "Título de teste",
                "Ana Silva",
                "Introduction",
                "Corpo revisto",
                "References",
                "Smith J. A paper. 2020.",
            ]
        )
        self.client.post(
            add_url,
            {
                "title": "Same name",
                "article_type": "research-article",
                "language": "en",
                "specific_use": "sps-1.10",
                "source_docx": SimpleUploadedFile(
                    "bn-2025-1834.docx",
                    first_payload,
                    content_type=content_type,
                ),
            },
        )
        self.client.post(
            add_url,
            {
                "title": "Same name revised",
                "article_type": "research-article",
                "language": "en",
                "specific_use": "sps-1.10",
                "source_docx": SimpleUploadedFile(
                    "bn-2025-1834.docx",
                    second_payload,
                    content_type=content_type,
                ),
            },
        )
        self.assertEqual(Manuscript.objects.count(), 2)
        self.assertTrue(Manuscript.objects.filter(title="Same name").exists())
        self.assertTrue(Manuscript.objects.filter(title="Same name revised").exists())


class ManuscriptBulkUploadTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="bulk_editor", email="bulk@example.com", password="secret"
        )
        self.client.force_login(user)
        self.list_url = reverse("wagtailsnippets_manuscript_manuscript:list")
        self.bulk_url = reverse("manuscript_bulk_upload")
        self.docx_content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def _sample_docx(self, filename, body="Corpo do artigo"):
        return SimpleUploadedFile(
            filename,
            make_docx_bytes(
                [
                    "Título de teste",
                    "Ana Silva",
                    "Received: 05/08/2025",
                    "Accepted: 27/03/2026",
                    "Introduction",
                    body,
                    "References",
                    "Smith J. A paper. 2020.",
                ]
            ),
            content_type=self.docx_content_type,
        )

    def test_manuscript_list_header_includes_bulk_upload_button(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.bulk_url)
        self.assertContains(response, "Bulk upload")

    def test_bulk_upload_get_renders_dropzone_and_wagtail_fileupload(self):
        response = self.client.get(self.bulk_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "drop-zone")
        self.assertContains(response, "jquery.fileupload.js")
        self.assertContains(response, "manuscript/js/bulk-upload.js")
        self.assertContains(response, f'data-redirect-url="{self.list_url}"')

    @patch("body.tasks.mark_body_text.apply_async")
    @patch("front.tasks.mark_front_text.apply_async")
    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_bulk_upload_ajax_creates_manuscript_with_stem_and_enqueues_marking(
        self, mock_back, mock_front, mock_body
    ):
        mock_back.return_value = MagicMock(id="task-bulk-back-1")
        upload = self._sample_docx("bn-2025-1834.docx")

        response = self.client.post(
            self.bulk_url,
            {"files[]": upload},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertFalse(payload["reused"])
        self.assertEqual(payload["title"], "bn-2025-1834")
        self.assertEqual(payload["redirect_url"], self.list_url)

        manuscript = Manuscript.objects.get(pk=payload["manuscript_id"])
        self.assertEqual(manuscript.title, "bn-2025-1834")
        self.assertEqual(manuscript.status, ManuscriptStatus.FRONT)
        self.assertEqual(manuscript.source_document.collection.name, "bn-2025-1834")
        self.assertIn("Corpo do artigo", manuscript.body_source_text)
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
        self.assertEqual(runs[ManuscriptMarkingPart.BACK].task_id, "task-bulk-back-1")
        self.assertEqual(
            runs[ManuscriptMarkingPart.FRONT].status,
            ManuscriptMarkingRunStatus.PENDING,
        )
        self.assertEqual(
            runs[ManuscriptMarkingPart.BODY].status,
            ManuscriptMarkingRunStatus.PENDING,
        )

    @patch("body.tasks.mark_body_text.apply_async")
    @patch("front.tasks.mark_front_text.apply_async")
    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_bulk_upload_ajax_remarks_same_bytes(
        self, mock_back, mock_front, mock_body
    ):
        mock_back.side_effect = [
            MagicMock(id="task-bulk-back-1"),
            MagicMock(id="task-bulk-back-2"),
        ]
        payload_bytes = make_docx_bytes(
            [
                "Título de teste",
                "Ana Silva",
                "Received: 05/08/2025",
                "Accepted: 27/03/2026",
                "Introduction",
                "Corpo do artigo",
                "References",
                "Smith J. A paper. 2020.",
            ]
        )
        first_upload = SimpleUploadedFile(
            "bn-2025-1834.docx",
            payload_bytes,
            content_type=self.docx_content_type,
        )
        first = self.client.post(
            self.bulk_url,
            {"files[]": first_upload},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        first_payload = first.json()
        manuscript = Manuscript.objects.get(pk=first_payload["manuscript_id"])
        manuscript.language = "es"
        manuscript.save(update_fields=["language"])
        second_upload = SimpleUploadedFile(
            "outro-nome.docx",
            payload_bytes,
            content_type=self.docx_content_type,
        )
        second = self.client.post(
            self.bulk_url,
            {"files[]": second_upload},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(second.status_code, 200)
        second_payload = second.json()
        self.assertTrue(second_payload["reused"])
        self.assertEqual(second_payload["manuscript_id"], manuscript.pk)
        self.assertEqual(Manuscript.objects.count(), 1)
        manuscript.refresh_from_db()
        self.assertEqual(manuscript.title, "outro-nome")
        self.assertEqual(manuscript.language, "es")
        self.assertEqual(mock_back.call_count, 2)
        self.assertEqual(
            ManuscriptMarkingRun.objects.get(
                manuscript=manuscript, part=ManuscriptMarkingPart.BACK
            ).task_id,
            "task-bulk-back-2",
        )

    @patch("body.tasks.mark_body_text.apply_async")
    @patch("front.tasks.mark_front_text.apply_async")
    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_bulk_upload_same_bytes_in_one_post_keeps_one_manuscript(
        self, mock_back, mock_front, mock_body
    ):
        mock_back.return_value = MagicMock(id="task-bulk-back")
        payload_bytes = make_docx_bytes(
            [
                "Título de teste",
                "Ana Silva",
                "Received: 05/08/2025",
                "Accepted: 27/03/2026",
                "Introduction",
                "Corpo do artigo",
                "References",
                "Smith J. A paper. 2020.",
            ]
        )
        response = self.client.post(
            self.bulk_url,
            {
                "files[]": [
                    SimpleUploadedFile(
                        "rsp-2026-0001.docx",
                        payload_bytes,
                        content_type=self.docx_content_type,
                    ),
                    SimpleUploadedFile(
                        "rsp-2026-0002.docx",
                        payload_bytes,
                        content_type=self.docx_content_type,
                    ),
                ]
            },
        )
        self.assertRedirects(response, self.list_url, fetch_redirect_response=False)
        self.assertEqual(Manuscript.objects.count(), 1)

    @patch("body.tasks.mark_body_text.apply_async")
    @patch("front.tasks.mark_front_text.apply_async")
    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_bulk_upload_multiple_files_redirects_to_manuscript_list(
        self, mock_back, mock_front, mock_body
    ):
        mock_back.return_value = MagicMock(id="task-bulk-back")
        first = self._sample_docx("rsp-2026-0001.docx")
        second = self._sample_docx("rsp-2026-0002.docx", body="Outro corpo do lote")

        response = self.client.post(
            self.bulk_url,
            {"files[]": [first, second]},
        )
        self.assertRedirects(
            response,
            self.list_url,
            fetch_redirect_response=False,
        )
        self.assertTrue(Manuscript.objects.filter(title="rsp-2026-0001").exists())
        self.assertTrue(Manuscript.objects.filter(title="rsp-2026-0002").exists())
        self.assertEqual(mock_back.call_count, 1)
        second_ms = Manuscript.objects.get(title="rsp-2026-0002")
        second_back = ManuscriptMarkingRun.objects.get(
            manuscript=second_ms, part=ManuscriptMarkingPart.BACK
        )
        self.assertEqual(second_back.status, ManuscriptMarkingRunStatus.PENDING)
        self.assertEqual(second_back.task_id, "")

    def test_bulk_upload_rejects_non_docx_file(self):
        invalid_file = SimpleUploadedFile(
            "invalid.txt",
            b"not a docx",
            content_type="text/plain",
        )
        response = self.client.post(
            self.bulk_url,
            {"files[]": invalid_file},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertIn("invalid.txt", payload["error_message"])
        self.assertEqual(Manuscript.objects.count(), 0)

    @patch("body.tasks.mark_body_text.apply_async")
    @patch("front.tasks.mark_front_text.apply_async")
    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_bulk_upload_adds_renames_and_deletes_package_figures(
        self, mock_back, mock_front, mock_body
    ):
        from io import BytesIO

        from PIL import Image as PILImage

        mock_back.return_value = MagicMock(id="task-bulk-back-fig")
        upload = self._sample_docx("bn-2025-1834.docx")
        response = self.client.post(
            self.bulk_url,
            {"files[]": upload},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("data-manuscript-package", payload["html"])
        self.assertEqual(
            payload["add_figures_url"],
            reverse("manuscript_api_add_figure", args=[payload["manuscript_id"]]),
        )

        manuscript = Manuscript.objects.get(pk=payload["manuscript_id"])
        manuscript.body_marked = {
            "sections": [
                {
                    "title": "Results",
                    "content": [
                        {
                            "type": "fig",
                            "id": "f1",
                            "label": "Figure 1",
                            "caption": "Map",
                        },
                        {
                            "type": "fig",
                            "id": "f2",
                            "label": "Figure 2",
                            "caption": "Chart",
                        },
                    ],
                    "sections": [],
                }
            ]
        }
        manuscript.save(update_fields=["body_marked"])

        png_buf = BytesIO()
        PILImage.new("RGB", (4, 4), color=(255, 0, 0)).save(png_buf, format="PNG")
        jpg_buf = BytesIO()
        PILImage.new("RGB", (4, 4), color=(0, 255, 0)).save(jpg_buf, format="JPEG")

        add_resp = self.client.post(
            payload["add_figures_url"],
            {
                "files[]": [
                    SimpleUploadedFile(
                        "arbitrary_chart.png",
                        png_buf.getvalue(),
                        content_type="image/png",
                    ),
                    SimpleUploadedFile(
                        "map_photo.jpg",
                        jpg_buf.getvalue(),
                        content_type="image/jpeg",
                    ),
                ]
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(add_resp.status_code, 200)
        add_data = add_resp.json()
        self.assertTrue(add_data["success"])
        self.assertEqual(len(add_data["figures"]), 2)
        self.assertEqual(add_data["figures"][0]["href"], "fig-1.jpg")
        self.assertEqual(add_data["figures"][0]["original_name"], "arbitrary_chart.png")
        self.assertEqual(add_data["figures"][1]["href"], "fig-2.jpg")
        self.assertEqual(add_data["figures"][1]["original_name"], "map_photo.jpg")

        first_fig_id = add_data["figures"][0]["id"]
        second_fig_id = add_data["figures"][1]["id"]

        rename_resp = self.client.post(
            reverse(
                "manuscript_api_update_figure",
                args=[manuscript.pk, first_fig_id],
            ),
            {"href": "fig-2"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(rename_resp.status_code, 200)
        rename_data = rename_resp.json()
        self.assertTrue(rename_data["success"])
        self.assertEqual(rename_data["href"], "fig-2.jpg")
        self.assertEqual(rename_data["number"], 2)

        figs_by_id = {
            fig.pk: fig for fig in manuscript.figure_files.select_related("image")
        }
        self.assertEqual(figs_by_id[first_fig_id].href, "fig-2.jpg")
        self.assertEqual(figs_by_id[first_fig_id].number, 2)
        self.assertEqual(
            figs_by_id[first_fig_id].image.title, f"{manuscript.pk} fig-2.jpg"
        )
        self.assertEqual(figs_by_id[second_fig_id].href, "fig-1.jpg")
        self.assertEqual(figs_by_id[second_fig_id].number, 1)

        manuscript.refresh_from_db()
        self.assertIn('xlink:href="fig-1.jpg"', manuscript.body_marked_xml)
        self.assertIn('xlink:href="fig-2.jpg"', manuscript.body_marked_xml)

        del_resp = self.client.post(
            reverse(
                "manuscript_api_delete_figure",
                args=[manuscript.pk, first_fig_id],
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(del_resp.status_code, 200)
        del_data = del_resp.json()
        self.assertTrue(del_data["success"])
        self.assertEqual(len(del_data["figures"]), 1)
        self.assertEqual(manuscript.figure_files.count(), 1)

        non_ajax_resp = self.client.post(
            reverse(
                "manuscript_api_update_figure",
                args=[manuscript.pk, second_fig_id],
            ),
            {"href": "fig-3"},
        )
        self.assertRedirects(
            non_ajax_resp,
            reverse("manuscript_step_body", args=[manuscript.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            manuscript.figure_files.get(pk=second_fig_id).href,
            "fig-3.jpg",
        )

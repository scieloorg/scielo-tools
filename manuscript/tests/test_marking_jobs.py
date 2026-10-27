from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from manuscript.models import (
    Manuscript,
    ManuscriptMarkingPart,
    ManuscriptMarkingRun,
    ManuscriptMarkingRunStatus,
    ManuscriptStatus,
)
from manuscript.services.marking import (
    MarkingError,
    save_body_marked,
    save_front_marked,
)
from manuscript.services.marking_jobs import (
    enqueue_back,
    enqueue_body,
    enqueue_front,
    enqueue_manuscript_marking,
    marking_status_payload,
)
from manuscript.services.workflow import WorkflowError, approve_front
from manuscript.tasks import (
    fail_marking_run,
    persist_back_result,
    persist_body_result,
    persist_front_result,
)


class MarkingJobsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.manuscript = Manuscript.objects.create(
            title="Async marking",
            status=ManuscriptStatus.FRONT,
            creator=self.user,
            front_source_text="Hello front",
            body_source_text="Hello body",
            references_source_text="Smith J. Nature. 2024.",
        )

    def _async_result(self):
        result = MagicMock()
        result.id = "task-1"
        return result

    @patch("front.tasks.mark_front_text.apply_async")
    def test_enqueue_front_calls_apply_async(self, mock_apply):
        mock_apply.return_value = self._async_result()
        run = enqueue_front(self.manuscript, user=self.user)
        self.assertEqual(run.status, ManuscriptMarkingRunStatus.PENDING)
        self.assertEqual(run.task_id, "task-1")
        self.assertEqual(mock_apply.call_args.kwargs["kwargs"]["text"], "Hello front")
        self.assertIn("link", mock_apply.call_args.kwargs)
        self.assertIn("link_error", mock_apply.call_args.kwargs)

    @patch("front.tasks.mark_front_text.apply_async")
    def test_enqueue_front_rejects_second_run(self, mock_apply):
        mock_apply.return_value = self._async_result()
        enqueue_front(self.manuscript, user=self.user)
        with self.assertRaises(MarkingError):
            enqueue_front(self.manuscript, user=self.user)
        self.assertEqual(mock_apply.call_count, 1)

    @patch("body.tasks.mark_body_text.apply_async")
    def test_enqueue_body_calls_apply_async(self, mock_apply):
        mock_apply.return_value = self._async_result()
        run = enqueue_body(self.manuscript, user=self.user)
        self.assertEqual(run.part, ManuscriptMarkingPart.BODY)
        self.assertEqual(mock_apply.call_args.kwargs["kwargs"]["text"], "Hello body")

    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_enqueue_back_calls_apply_async(self, mock_apply):
        mock_apply.return_value = self._async_result()
        run = enqueue_back(self.manuscript, user=self.user)
        self.assertEqual(run.part, ManuscriptMarkingPart.BACK)
        self.assertEqual(
            mock_apply.call_args.kwargs["kwargs"]["texts"],
            ["Smith J. Nature. 2024."],
        )

    def test_persist_front_and_body_keep_assembled_xml(self):
        from manuscript.models import ManuscriptReference

        ManuscriptReference.objects.create(
            manuscript=self.manuscript,
            mixed_citation="Smith J. Nature. 2024.",
            marked={"reftype": "journal", "source": "Nature"},
            marked_xml=(
                '<element-citation publication-type="journal">'
                "<source>Nature</source>"
                "</element-citation>"
            ),
            sort_order=0,
        )
        ManuscriptMarkingRun.objects.create(
            manuscript=self.manuscript,
            part=ManuscriptMarkingPart.FRONT,
            status=ManuscriptMarkingRunStatus.PENDING,
        )
        ManuscriptMarkingRun.objects.create(
            manuscript=self.manuscript,
            part=ManuscriptMarkingPart.BODY,
            status=ManuscriptMarkingRunStatus.PENDING,
        )
        persist_front_result(
            {
                "data": {
                    "titles": [
                        {"kind": "main", "text": "Front title", "language": "en"}
                    ]
                }
            },
            self.manuscript.pk,
            self.user.pk,
        )
        persist_body_result(
            {
                "data": {
                    "sections": [
                        {
                            "title": "Intro",
                            "content": [{"type": "p", "text": "Hello"}],
                            "sections": [],
                        }
                    ]
                }
            },
            self.manuscript.pk,
            self.user.pk,
        )
        self.manuscript.refresh_from_db()
        self.assertIn("Front title", self.manuscript.front_marked_xml)
        self.assertIn("Hello", self.manuscript.body_marked_xml)
        self.assertTrue((self.manuscript.assembled_xml or "").strip())
        front_run = ManuscriptMarkingRun.objects.get(
            manuscript=self.manuscript, part=ManuscriptMarkingPart.FRONT
        )
        self.assertEqual(front_run.status, ManuscriptMarkingRunStatus.DONE)
        self.assertEqual(front_run.endpoints, "local")
        body_run = ManuscriptMarkingRun.objects.get(
            manuscript=self.manuscript, part=ManuscriptMarkingPart.BODY
        )
        self.assertEqual(body_run.endpoints, "local")

    def test_persist_back_records_both_endpoints(self):
        ManuscriptMarkingRun.objects.create(
            manuscript=self.manuscript,
            part=ManuscriptMarkingPart.BACK,
            status=ManuscriptMarkingRunStatus.PENDING,
        )
        persist_back_result(
            {
                "items": [
                    {
                        "mixed_citation": "Smith J. Nature. 2024.",
                        "data": {"reftype": "journal", "source": "Nature"},
                    }
                ],
                "endpoints": "both",
            },
            self.manuscript.pk,
            self.user.pk,
        )
        run = ManuscriptMarkingRun.objects.get(
            manuscript=self.manuscript, part=ManuscriptMarkingPart.BACK
        )
        self.assertEqual(run.status, ManuscriptMarkingRunStatus.DONE)
        self.assertEqual(run.endpoints, "both")
        payload = marking_status_payload(self.manuscript)
        self.assertEqual(payload["back"]["endpoints"], "both")

    def test_status_payload_defaults_to_idle(self):
        payload = marking_status_payload(self.manuscript)
        self.assertEqual(payload["front"]["status"], ManuscriptMarkingRunStatus.IDLE)
        self.assertEqual(payload["body"]["status"], ManuscriptMarkingRunStatus.IDLE)
        self.assertEqual(payload["back"]["status"], ManuscriptMarkingRunStatus.IDLE)
        self.assertIsNone(payload["front"]["percent"])

    def test_status_payload_done_percent_is_100(self):
        ManuscriptMarkingRun.objects.create(
            manuscript=self.manuscript,
            part=ManuscriptMarkingPart.FRONT,
            status=ManuscriptMarkingRunStatus.DONE,
        )
        payload = marking_status_payload(self.manuscript)
        self.assertEqual(payload["front"]["status"], ManuscriptMarkingRunStatus.DONE)
        self.assertEqual(payload["front"]["percent"], 100)

    def test_status_payload_running_percent_defaults_to_zero(self):
        ManuscriptMarkingRun.objects.create(
            manuscript=self.manuscript,
            part=ManuscriptMarkingPart.FRONT,
            status=ManuscriptMarkingRunStatus.RUNNING,
        )
        payload = marking_status_payload(self.manuscript)
        self.assertEqual(payload["front"]["status"], ManuscriptMarkingRunStatus.RUNNING)
        self.assertEqual(payload["front"]["percent"], 0)

    def test_approve_front_blocked_while_running(self):
        ManuscriptMarkingRun.objects.create(
            manuscript=self.manuscript,
            part=ManuscriptMarkingPart.FRONT,
            status=ManuscriptMarkingRunStatus.RUNNING,
        )
        with self.assertRaises(WorkflowError):
            approve_front(self.manuscript, user=self.user)

    def test_select_for_update_refresh_keeps_both_parts(self):
        save_front_marked(
            self.manuscript,
            {"titles": [{"kind": "main", "text": "A", "language": "en"}]},
            user=self.user,
        )
        save_body_marked(
            self.manuscript,
            {
                "sections": [
                    {
                        "title": "Intro",
                        "content": [{"type": "p", "text": "B"}],
                        "sections": [],
                    }
                ]
            },
            user=self.user,
        )
        self.manuscript.refresh_from_db()
        self.assertIn("A", self.manuscript.front_marked_xml)
        self.assertIn("B", self.manuscript.body_marked_xml)

    @patch("manuscript.tasks.generate_manuscript_html_task.apply_async")
    @patch("manuscript.tasks.generate_manuscript_pdf_task.apply_async")
    @patch("manuscript.tasks.run_manuscript_validation_task.apply_async")
    @patch("body.tasks.mark_body_text.apply_async")
    @patch("front.tasks.mark_front_text.apply_async")
    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_enqueue_manuscript_marking_runs_back_then_front_then_body(
        self,
        mock_back,
        mock_front,
        mock_body,
        mock_val,
        mock_pdf,
        mock_html,
    ):
        back_result = MagicMock()
        back_result.id = "task-back"
        front_result = MagicMock()
        front_result.id = "task-front"
        body_result = MagicMock()
        body_result.id = "task-body"
        val_result = MagicMock()
        val_result.id = "task-val"
        pdf_result = MagicMock()
        pdf_result.id = "task-pdf"
        html_result = MagicMock()
        html_result.id = "task-html"
        mock_back.return_value = back_result
        mock_front.return_value = front_result
        mock_body.return_value = body_result
        mock_val.return_value = val_result
        mock_pdf.return_value = pdf_result
        mock_html.return_value = html_result

        first_run = enqueue_manuscript_marking(self.manuscript, user=self.user)
        self.assertEqual(first_run.part, ManuscriptMarkingPart.BACK)
        self.assertEqual(first_run.task_id, "task-back")
        mock_back.assert_called_once()
        mock_front.assert_not_called()
        mock_body.assert_not_called()

        runs = {
            run.part: run
            for run in ManuscriptMarkingRun.objects.filter(manuscript=self.manuscript)
        }
        self.assertEqual(
            runs[ManuscriptMarkingPart.BACK].status,
            ManuscriptMarkingRunStatus.PENDING,
        )
        self.assertEqual(runs[ManuscriptMarkingPart.BACK].task_id, "task-back")
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

        persist_back_result(
            {
                "items": [
                    {
                        "mixed_citation": "Smith J. Nature. 2024.",
                        "data": {"reftype": "journal", "source": "Nature"},
                    }
                ],
                "endpoints": "local",
            },
            self.manuscript.pk,
            self.user.pk,
        )
        mock_front.assert_called_once()
        mock_body.assert_not_called()
        mock_val.assert_not_called()
        front_run = ManuscriptMarkingRun.objects.get(
            manuscript=self.manuscript, part=ManuscriptMarkingPart.FRONT
        )
        self.assertEqual(front_run.task_id, "task-front")

        persist_front_result(
            {
                "data": {
                    "titles": [
                        {"kind": "main", "text": "Front title", "language": "en"}
                    ]
                }
            },
            self.manuscript.pk,
            self.user.pk,
        )
        mock_body.assert_called_once()
        mock_val.assert_not_called()
        body_run = ManuscriptMarkingRun.objects.get(
            manuscript=self.manuscript, part=ManuscriptMarkingPart.BODY
        )
        self.assertEqual(body_run.task_id, "task-body")

        persist_body_result(
            {
                "data": {
                    "sections": [
                        {
                            "title": "Intro",
                            "content": [{"type": "p", "text": "Hello"}],
                            "sections": [],
                        }
                    ]
                }
            },
            self.manuscript.pk,
            self.user.pk,
        )
        for part in (
            ManuscriptMarkingPart.BACK,
            ManuscriptMarkingPart.FRONT,
            ManuscriptMarkingPart.BODY,
        ):
            run = ManuscriptMarkingRun.objects.get(
                manuscript=self.manuscript, part=part
            )
            self.assertEqual(run.status, ManuscriptMarkingRunStatus.DONE)
        mock_val.assert_called_once()
        mock_pdf.assert_called_once()
        mock_html.assert_called_once()
        val_run = ManuscriptMarkingRun.objects.get(
            manuscript=self.manuscript, part=ManuscriptMarkingPart.VALIDATE
        )
        pdf_run = ManuscriptMarkingRun.objects.get(
            manuscript=self.manuscript, part=ManuscriptMarkingPart.PDF
        )
        html_run = ManuscriptMarkingRun.objects.get(
            manuscript=self.manuscript, part=ManuscriptMarkingPart.HTML
        )
        self.assertEqual(val_run.task_id, "task-val")
        self.assertEqual(pdf_run.task_id, "task-pdf")
        self.assertEqual(html_run.task_id, "task-html")

    @patch("body.tasks.mark_body_text.apply_async")
    @patch("front.tasks.mark_front_text.apply_async")
    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_fail_marking_run_advances_queue_to_next_part(
        self, mock_back, mock_front, mock_body
    ):
        back_result = MagicMock()
        back_result.id = "task-back"
        front_result = MagicMock()
        front_result.id = "task-front"
        body_result = MagicMock()
        body_result.id = "task-body"
        mock_back.return_value = back_result
        mock_front.return_value = front_result
        mock_body.return_value = body_result

        enqueue_manuscript_marking(self.manuscript, user=self.user)
        fail_marking_run(
            None,
            exc="Back LLM failed",
            manuscript_id=self.manuscript.pk,
            part=ManuscriptMarkingPart.BACK,
        )
        back_run = ManuscriptMarkingRun.objects.get(
            manuscript=self.manuscript, part=ManuscriptMarkingPart.BACK
        )
        self.assertEqual(back_run.status, ManuscriptMarkingRunStatus.ERROR)
        mock_front.assert_called_once()
        mock_body.assert_not_called()

        fail_marking_run(
            None,
            exc="Front LLM failed",
            manuscript_id=self.manuscript.pk,
            part=ManuscriptMarkingPart.FRONT,
        )
        front_run = ManuscriptMarkingRun.objects.get(
            manuscript=self.manuscript, part=ManuscriptMarkingPart.FRONT
        )
        self.assertEqual(front_run.status, ManuscriptMarkingRunStatus.ERROR)
        mock_body.assert_called_once()

    @patch("body.tasks.mark_body_text.apply_async")
    @patch("front.tasks.mark_front_text.apply_async")
    @patch("reference.tasks.mark_reference_texts_task.apply_async")
    def test_enqueue_manuscript_marking_starts_front_when_no_references(
        self, mock_back, mock_front, mock_body
    ):
        front_result = MagicMock()
        front_result.id = "task-front"
        mock_front.return_value = front_result
        self.manuscript.references_source_text = ""
        self.manuscript.save(update_fields=["references_source_text"])

        first_run = enqueue_manuscript_marking(self.manuscript, user=self.user)
        self.assertEqual(first_run.part, ManuscriptMarkingPart.FRONT)
        self.assertEqual(first_run.task_id, "task-front")
        mock_back.assert_not_called()
        mock_front.assert_called_once()
        mock_body.assert_not_called()
        self.assertFalse(
            ManuscriptMarkingRun.objects.filter(
                manuscript=self.manuscript, part=ManuscriptMarkingPart.BACK
            ).exists()
        )

    @patch(
        "manuscript.services.assembly.generate_packtools_pdf",
        return_value=b"%PDF-1.4",
    )
    @patch("xml_manager.services.utils.validate_zip", return_value=([], []))
    def test_post_marking_tasks_generate_validation_pdf_and_html_without_issn(
        self, _mock_validate, _mock_pdf
    ):
        from manuscript.tasks import (
            generate_manuscript_html_task,
            generate_manuscript_pdf_task,
            run_manuscript_validation_task,
        )

        save_front_marked(
            self.manuscript,
            {"titles": [{"kind": "main", "text": "No ISSN title", "language": "en"}]},
            user=self.user,
        )
        save_body_marked(
            self.manuscript,
            {
                "sections": [
                    {
                        "title": "Intro",
                        "content": [{"type": "p", "text": "Body text."}],
                        "sections": [],
                    }
                ]
            },
            user=self.user,
        )
        ManuscriptMarkingRun.objects.create(
            manuscript=self.manuscript,
            part=ManuscriptMarkingPart.VALIDATE,
            status=ManuscriptMarkingRunStatus.PENDING,
        )
        ManuscriptMarkingRun.objects.create(
            manuscript=self.manuscript,
            part=ManuscriptMarkingPart.PDF,
            status=ManuscriptMarkingRunStatus.PENDING,
        )
        ManuscriptMarkingRun.objects.create(
            manuscript=self.manuscript,
            part=ManuscriptMarkingPart.HTML,
            status=ManuscriptMarkingRunStatus.PENDING,
        )
        ManuscriptMarkingRun.objects.create(
            manuscript=self.manuscript,
            part=ManuscriptMarkingPart.PACKAGE,
            status=ManuscriptMarkingRunStatus.PENDING,
        )
        run_manuscript_validation_task.run(self.manuscript.pk, self.user.pk)
        generate_manuscript_pdf_task.run(self.manuscript.pk, self.user.pk)
        generate_manuscript_html_task.run(self.manuscript.pk, self.user.pk)

        self.manuscript.refresh_from_db()
        self.assertIsNotNone(self.manuscript.validation_id)
        self.assertIsNotNone(self.manuscript.sps_package_id)
        self.assertIsNotNone(self.manuscript.generated_pdf_id)
        self.assertIsNotNone(self.manuscript.generated_html_id)
        payload = marking_status_payload(self.manuscript)
        self.assertEqual(payload["validate"]["status"], ManuscriptMarkingRunStatus.DONE)
        self.assertEqual(payload["validate"]["percent"], 100)
        self.assertEqual(payload["package"]["status"], ManuscriptMarkingRunStatus.DONE)
        self.assertEqual(payload["package"]["percent"], 100)


class MarkingStatusViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(self.user)
        self.manuscript = Manuscript.objects.create(
            title="Status",
            status=ManuscriptStatus.FRONT,
            creator=self.user,
            front_source_text="Hello front",
        )

    def test_status_endpoint_returns_parts(self):
        response = self.client.get(
            reverse("manuscript_api_marking_status", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["front"]["status"], "idle")
        self.assertEqual(data["body"]["status"], "idle")
        self.assertEqual(data["back"]["status"], "idle")

    @patch("front.tasks.mark_front_text.apply_async")
    def test_mark_post_enqueues_and_does_not_wait(self, mock_apply):
        result = MagicMock()
        result.id = "queued-1"
        mock_apply.return_value = result
        url = reverse("manuscript_step_front", args=[self.manuscript.pk])
        response = self.client.post(
            url,
            {"action": "mark", "source_text": "Hello front text"},
        )
        self.assertRedirects(response, url, fetch_redirect_response=False)
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.front_source_text, "Hello front text")
        self.assertEqual(self.manuscript.front_marked_xml, "")
        mock_apply.assert_called_once()
        follow = self.client.get(url)
        self.assertContains(follow, "Front marking started.")
        self.assertContains(follow, 'data-marking-part="front"')
        self.assertContains(follow, "is-running")
        self.assertContains(follow, "manuscript-marking-state")
        self.assertContains(follow, 'data-marking-submit="front"')

    def test_front_step_includes_status_url(self):
        response = self.client.get(
            reverse("manuscript_step_front", args=[self.manuscript.pk])
        )
        self.assertContains(response, "/api/marking-status/")
        self.assertContains(response, 'data-marking-part="front"')
        self.assertContains(response, "manuscript-wizard__step-meter")
        self.assertNotContains(response, "manuscript-marking-overlay")

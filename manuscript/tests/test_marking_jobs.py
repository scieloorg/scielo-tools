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
    marking_status_payload,
)
from manuscript.services.workflow import WorkflowError, approve_front
from manuscript.tasks import persist_body_result, persist_front_result


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

    def test_status_payload_defaults_to_idle(self):
        payload = marking_status_payload(self.manuscript)
        self.assertEqual(payload["front"]["status"], ManuscriptMarkingRunStatus.IDLE)
        self.assertEqual(payload["body"]["status"], ManuscriptMarkingRunStatus.IDLE)
        self.assertEqual(payload["back"]["status"], ManuscriptMarkingRunStatus.IDLE)
        self.assertIsNone(payload["front"]["percent"])

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

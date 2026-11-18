from django.contrib.auth import get_user_model
from django.test import TestCase

from manuscript.models import Manuscript, ManuscriptStatus
from manuscript.services.workflow import (
    WorkflowError,
    approve_back,
    approve_body,
    approve_front,
    open_step,
)

User = get_user_model()


class WorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="secret")
        self.manuscript = Manuscript.objects.create(
            title="Test article",
            status=ManuscriptStatus.DRAFT,
            creator=self.user,
        )

    def test_open_step_moves_to_front(self):
        open_step(self.manuscript, ManuscriptStatus.FRONT, user=self.user)
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.status, ManuscriptStatus.FRONT)

    def test_approve_front_moves_to_body(self):
        open_step(self.manuscript, ManuscriptStatus.FRONT, user=self.user)
        approve_front(self.manuscript, user=self.user)
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.status, ManuscriptStatus.BODY)
        self.assertIsNotNone(self.manuscript.front_approved_at)

    def test_approve_body_requires_body_status(self):
        with self.assertRaises(WorkflowError):
            approve_body(self.manuscript, user=self.user)

    def test_full_workflow_to_assembled(self):
        open_step(self.manuscript, ManuscriptStatus.FRONT, user=self.user)
        approve_front(self.manuscript, user=self.user)
        approve_body(self.manuscript, user=self.user)
        approve_back(self.manuscript, user=self.user)
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.status, ManuscriptStatus.ASSEMBLED)

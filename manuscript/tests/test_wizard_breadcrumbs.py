from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from manuscript.models import Manuscript, ManuscriptStatus


class WizardBreadcrumbTests(TestCase):
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

    def test_front_step_shows_breadcrumb_to_manuscripts_list(self):
        response = self.client.get(
            reverse("manuscript_step_front", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="Breadcrumb"')
        self.assertContains(response, "Toggle breadcrumbs")
        self.assertContains(response, 'data-controller="w-breadcrumbs"')
        self.assertContains(response, "Home")
        self.assertContains(response, "Manuscripts")
        self.assertContains(response, self.manuscript.title)
        self.assertContains(
            response, reverse("wagtailsnippets_manuscript_manuscript:list")
        )
        self.assertContains(response, reverse("wagtailadmin_home"))

    def test_validate_step_keeps_the_same_breadcrumb(self):
        response = self.client.get(
            reverse("manuscript_step_validate", args=[self.manuscript.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="Breadcrumb"')
        self.assertContains(response, "Manuscripts")
        self.assertContains(response, self.manuscript.title)

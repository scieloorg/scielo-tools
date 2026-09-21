import json
import re

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from wagtail.admin.site_summary import PagesSummaryItem, SiteSummaryPanel

from manuscript.models import Manuscript
from manuscript.wagtail_hooks import ManuscriptsSummaryItem

User = get_user_model()


class AdminHomeTests(TestCase):
    def test_home_hides_wagtail_editor_guide_link(self):
        user = User.objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("wagtailadmin_home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "editor guide")
        self.assertContains(response, "Account")
        self.assertContains(response, '"name": "search-home"')
        self.assertContains(response, '"label": "Buscar"')
        self.assertContains(
            response,
            'placeholder="Pesquisar por manuscritos, documentos(docx), imagens"',
        )
        self.assertContains(
            response,
            f'action="{reverse("scielo_admin_search")}"',
        )
        self.assertContains(response, 'id="id_q"')
        self.assertContains(response, "autofocus")
        self.assertContains(response, 'document.getElementById("id_q")?.focus();')
        self.assertNotContains(response, "Search all pages")
        self.assertNotContains(response, "wagtailadmin_explore")

    def test_home_hides_pages_summary_item(self):
        user = User.objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)
        request = RequestFactory().get(reverse("wagtailadmin_home"))
        request.user = user
        panel = SiteSummaryPanel(request)
        self.assertFalse(
            any(isinstance(item, PagesSummaryItem) for item in panel.summary_items)
        )
        self.assertIsInstance(panel.summary_items[0], ManuscriptsSummaryItem)
        response = self.client.get(reverse("wagtailadmin_home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "icon-doc-empty")
        self.assertContains(response, "icon-manuscript")
        self.assertContains(response, "0 Manuscripts")
        self.assertContains(
            response, reverse("wagtailsnippets_manuscript_manuscript:list")
        )
        self.assertContains(response, "icon-image")
        self.assertContains(response, "icon-doc-full")
        self.assertContains(response, "Images")
        self.assertContains(response, "Documents")

    def test_home_shows_manuscripts_count(self):
        user = User.objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)
        Manuscript.objects.create(title="First")
        Manuscript.objects.create(title="Second")
        response = self.client.get(reverse("wagtailadmin_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 Manuscripts")
        self.assertNotContains(response, "0 Manuscripts")

    def test_home_hides_pages_snippets_and_references_menu_items(self):
        user = User.objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("wagtailadmin_home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        match = re.search(
            r'<script id="wagtail-sidebar-props" '
            r'type="application/json">(.*?)</script>',
            html,
        )
        self.assertIsNotNone(match)
        payload = json.loads(match.group(1))
        main_names = [
            item["_args"][0]["name"] for item in payload["modules"][2]["_args"][0]
        ]
        for name in ("explorer", "snippets", "reference"):
            self.assertNotIn(name, main_names)
            self.assertNotContains(response, f'"name": "{name}"')

    def test_home_puts_reports_settings_help_with_account_menu(self):
        user = User.objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("wagtailadmin_home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        match = re.search(
            r'<script id="wagtail-sidebar-props" '
            r'type="application/json">(.*?)</script>',
            html,
        )
        self.assertIsNotNone(match)
        payload = json.loads(match.group(1))
        main_names = [
            item["_args"][0]["name"] for item in payload["modules"][2]["_args"][0]
        ]
        account_names = [
            item["_args"][0]["name"] for item in payload["modules"][2]["_args"][1]
        ]
        for name in ("reports", "settings", "help"):
            self.assertNotIn(name, main_names)
            self.assertIn(name, account_names)
        self.assertEqual(account_names[0], "account")
        self.assertEqual(account_names[-1], "logout")
        self.assertLess(account_names.index("account"), account_names.index("reports"))
        self.assertLess(account_names.index("help"), account_names.index("logout"))

    def test_home_main_menu_follows_configured_order(self):
        user = User.objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("wagtailadmin_home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        match = re.search(
            r'<script id="wagtail-sidebar-props" '
            r'type="application/json">(.*?)</script>',
            html,
        )
        self.assertIsNotNone(match)
        payload = json.loads(match.group(1))
        main_names = [
            item["_args"][0]["name"] for item in payload["modules"][2]["_args"][0]
        ]
        expected = [
            "manuscript",
            "sps_package_validation",
            "images",
            "documents",
        ]
        positions = [main_names.index(name) for name in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(main_names[0], "search-home")

    @override_settings(WEBAPP_VERSION="v0.0.3")
    def test_home_account_summary_shows_webapp_version_link(self):
        user = User.objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("wagtailadmin_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Account")
        self.assertContains(response, "custom-admin-version")
        self.assertContains(response, ">v0.0.3</a>")
        self.assertContains(
            response,
            'href="https://github.com/scieloorg/scielo-tools/releases/tag/v0.0.3"',
        )
        html = response.content.decode()
        self.assertLess(html.index(">Account</a>"), html.index(">v0.0.3</a>"))

    @override_settings(WEBAPP_VERSION="0.0.0")
    def test_home_placeholder_version_is_not_a_tag_link(self):
        user = User.objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("wagtailadmin_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ">0.0.0</span>")
        self.assertNotContains(response, "releases/tag/")

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.finders import find
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

User = get_user_model()


class AdminLogoTests(TestCase):
    def test_login_shows_color_scielo_logo(self):
        response = self.client.get(reverse("wagtailadmin_login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'viewBox="0 0 204 200"')
        self.assertContains(response, 'aria-label="SciELO"')
        self.assertContains(response, "custom-admin-logo--login")
        self.assertContains(response, 'class="custom-admin-logo-label"')
        self.assertContains(response, ">Tools</span>")
        self.assertNotContains(response, ">SciELO Tools</span>")
        self.assertNotContains(response, "core_settings/img/logo-scielo.svg")
        self.assertContains(response, "core_settings/img/favicon.svg")
        self.assertNotContains(response, "wagtailadmin/images/favicon.ico")
        self.assertNotContains(response, "vendor/scielo-ds/img/favicons/")

    def test_admin_sidebar_shows_color_scielo_logo(self):
        user = User.objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)
        response = self.client.get(reverse("wagtailadmin_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'viewBox="0 0 204 200"')
        self.assertContains(response, 'aria-label="SciELO"')
        self.assertContains(response, "data-wagtail-sidebar-branding-logo")
        self.assertContains(response, 'class="custom-admin-logo-label"')
        self.assertContains(response, ">Tools</span>")
        self.assertNotContains(response, ">SciELO Tools</span>")
        self.assertNotContains(response, "core_settings/img/logo-scielo.svg")
        self.assertContains(response, "core_settings/img/favicon.svg")
        self.assertNotContains(response, "wagtailadmin/images/favicon.ico")
        self.assertNotContains(response, "vendor/scielo-ds/img/favicons/")

    @override_settings(WEBAPP_VERSION="v0.0.3-qa")
    def test_login_shows_webapp_version_link_below_tools(self):
        response = self.client.get(reverse("wagtailadmin_login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "custom-admin-logo-meta")
        self.assertContains(response, "custom-admin-version--login")
        self.assertContains(response, ">v0.0.3-qa</a>")
        self.assertContains(
            response,
            'href="https://github.com/scieloorg/scielo-tools/releases/tag/v0.0.3-qa"',
        )
        html = response.content.decode()
        self.assertLess(html.index(">Tools</span>"), html.index(">v0.0.3-qa</a>"))

    @override_settings(WEBAPP_VERSION="0.0.0")
    def test_login_placeholder_version_is_not_a_tag_link(self):
        response = self.client.get(reverse("wagtailadmin_login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ">0.0.0</span>")
        self.assertNotContains(response, "releases/tag/")

    def test_favicon_svg_is_published(self):
        self.assertIsNotNone(find("core_settings/img/favicon.svg"))

    def test_public_templates_use_scielo_favicon(self):
        request = RequestFactory().get("/")
        html = render_to_string("404.html", request=request)
        self.assertIn("core_settings/img/favicon.svg", html)
        self.assertNotIn("vendor/scielo-ds/img/favicons/", html)
        self.assertNotIn("wagtailadmin/images/favicon.ico", html)

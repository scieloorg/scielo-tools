from django.test import TestCase
from django.urls import reverse


class HomePageRedirectTests(TestCase):
    def test_root_url_redirects_to_admin(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("wagtailadmin_home"))

    def test_localized_root_urls_redirect_to_admin(self):
        for path in ("/en/", "/pt-br/", "/es/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, reverse("wagtailadmin_home"))

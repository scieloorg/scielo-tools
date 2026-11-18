from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from wagtail.snippets.models import get_snippet_models

from manuscript.forms import ManuscriptCreateForm
from manuscript.models import OriginalLanguage
from manuscript.sps_languages import SPS_ORIGINAL_LANGUAGES


class OriginalLanguageSnippetTests(TestCase):
    def test_scielo_languages_are_seeded(self):
        codes = set(OriginalLanguage.objects.values_list("code", flat=True))
        expected = {code for code, _name in SPS_ORIGINAL_LANGUAGES}
        self.assertEqual(codes, expected)
        self.assertEqual(len(expected), 3)

    def test_original_language_is_registered_as_snippet(self):
        self.assertIn(OriginalLanguage, get_snippet_models())

    def test_str_includes_name_and_code(self):
        language = OriginalLanguage.objects.get(code="pt")
        self.assertEqual(str(language), "Português (pt)")


class ManuscriptOriginalLanguageFormTests(TestCase):
    def test_create_form_uses_closed_list_from_snippets(self):
        form = ManuscriptCreateForm()
        field = form.fields["language"]
        self.assertEqual(field.__class__.__name__, "ChoiceField")
        codes = [code for code, _label in field.choices]
        expected = list(
            OriginalLanguage.objects.order_by("sort_order", "code").values_list(
                "code", flat=True
            )
        )
        self.assertEqual(codes, expected)
        self.assertEqual(field.initial, "pt")
        self.assertEqual(str(field.label), "Original language")

    def test_create_form_rejects_unknown_language(self):
        form = ManuscriptCreateForm(
            data={
                "title": "Sample",
                "article_type": "research-article",
                "language": "xx",
                "specific_use": "sps-1.10",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("language", form.errors)

    def test_create_form_accepts_seeded_language(self):
        form = ManuscriptCreateForm(
            data={
                "title": "Sample",
                "article_type": "research-article",
                "language": "es",
                "specific_use": "sps-1.10",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        manuscript = form.save()
        self.assertEqual(manuscript.language, "es")

    def test_new_snippet_appears_in_closed_list(self):
        OriginalLanguage.objects.create(
            code="fr",
            name="Français",
            sort_order=99,
        )
        form = ManuscriptCreateForm()
        codes = [code for code, _label in form.fields["language"].choices]
        self.assertIn("fr", codes)


class ManuscriptOriginalLanguageAdminTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)

    def test_create_page_renders_language_select(self):
        response = self.client.get(reverse("wagtailsnippets_manuscript_manuscript:add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="language"')
        self.assertContains(response, "Original language")
        self.assertContains(response, "<select")
        self.assertContains(response, "Português (pt)")
        self.assertContains(response, "English (en)")
        self.assertContains(response, "Español (es)")
        self.assertNotContains(response, 'name="language" type="text"')

    def test_original_language_snippet_list_shows_seeded_codes(self):
        response = self.client.get(
            reverse("wagtailsnippets_manuscript_originallanguage:list")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pt")
        self.assertContains(response, "en")
        self.assertContains(response, "es")

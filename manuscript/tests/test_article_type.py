from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from wagtail.snippets.models import get_snippet_models

from manuscript.forms import ManuscriptCreateForm
from manuscript.models import ArticleType, Manuscript
from manuscript.sps_article_types import SPS_ARTICLE_TYPES


class ArticleTypeSnippetTests(TestCase):
    def test_sps_1_10_types_are_seeded(self):
        codes = set(ArticleType.objects.values_list("code", flat=True))
        expected = {code for code, _name, _description in SPS_ARTICLE_TYPES}
        self.assertEqual(codes, expected)
        self.assertEqual(len(expected), 18)

    def test_article_type_is_registered_as_snippet(self):
        self.assertIn(ArticleType, get_snippet_models())

    def test_str_includes_name_and_code(self):
        article_type = ArticleType.objects.get(code="research-article")
        self.assertEqual(str(article_type), "Artigo original (research-article)")


class ManuscriptArticleTypeFormTests(TestCase):
    def test_create_form_uses_closed_list_from_snippets(self):
        form = ManuscriptCreateForm()
        field = form.fields["article_type"]
        self.assertEqual(field.__class__.__name__, "ChoiceField")
        codes = [code for code, _label in field.choices]
        expected = list(
            ArticleType.objects.order_by("sort_order", "code").values_list(
                "code", flat=True
            )
        )
        self.assertEqual(codes, expected)
        self.assertEqual(field.initial, "research-article")

    def test_create_form_rejects_unknown_article_type(self):
        form = ManuscriptCreateForm(
            data={
                "title": "Sample",
                "article_type": "not-a-sps-type",
                "language": "en",
                "specific_use": "sps-1.10",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("article_type", form.errors)

    def test_create_form_accepts_seeded_article_type(self):
        form = ManuscriptCreateForm(
            data={
                "title": "Sample",
                "article_type": "review-article",
                "language": "en",
                "specific_use": "sps-1.10",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        manuscript = form.save()
        self.assertEqual(manuscript.article_type, "review-article")

    def test_new_snippet_appears_in_closed_list(self):
        ArticleType.objects.create(
            code="custom-type",
            name="Tipo customizado",
            sort_order=99,
        )
        form = ManuscriptCreateForm()
        codes = [code for code, _label in form.fields["article_type"].choices]
        self.assertIn("custom-type", codes)


class ManuscriptSpsVersionFormTests(TestCase):
    def test_create_form_defaults_sps_version_to_1_10(self):
        form = ManuscriptCreateForm()
        field = form.fields["specific_use"]
        self.assertEqual(str(field.label), "SPS version")
        self.assertEqual(field.initial, "sps-1.10")

    def test_manuscript_defaults_specific_use_to_sps_1_10(self):
        manuscript = Manuscript.objects.create(title="Sample")
        self.assertEqual(manuscript.specific_use, "sps-1.10")


class ManuscriptArticleTypeAdminTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)

    def test_create_page_renders_article_type_select(self):
        response = self.client.get(reverse("wagtailsnippets_manuscript_manuscript:add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="article_type"')
        self.assertContains(response, "<select")
        self.assertContains(response, "research-article")
        self.assertContains(response, "review-article")
        self.assertNotContains(response, 'name="article_type" type="text"')
        self.assertContains(response, "SPS version")
        self.assertContains(response, "sps-1.10")

    def test_article_type_snippet_list_shows_seeded_codes(self):
        response = self.client.get(
            reverse("wagtailsnippets_manuscript_articletype:list")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "research-article")
        self.assertContains(response, "addendum")
        self.assertContains(response, "referee-report")

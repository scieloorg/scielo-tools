from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import RequestFactory, TestCase
from django.urls import reverse
from wagtail import hooks
from wagtail.admin.search import admin_search_areas
from wagtail.documents.models import Document
from wagtail.images import get_image_model
from wagtail.images.tests.utils import get_test_image_file
from wagtail.models import Page

from core.home.models import HomePage
from core_settings.wagtail_hooks import SCIELO_SEARCH_AREA_NAME
from manuscript.models import ArticleType, Manuscript
from manuscript.services.workflow import current_step_url_name
from reference.models import Reference
from xml_manager.models import SPSPackageValidation

User = get_user_model()


class AdminSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(self.user)
        self.search_url = reverse("scielo_admin_search")

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(self.search_url, {"q": "term"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("wagtailadmin_login"), response.url)

    def test_empty_query_does_not_list_existing_items(self):
        manuscript = Manuscript.objects.create(title="Existing manuscript")
        response = self.client.get(self.search_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'placeholder="Pesquisar por manuscritos, documentos(docx), imagens"',
        )
        self.assertContains(response, f'action="{self.search_url}"')
        self.assertNotContains(response, manuscript.title)
        self.assertNotContains(response, "Manuscripts (")
        self.assertNotContains(response, "No manuscripts found.")

    def test_search_returns_manuscripts_images_and_documents_only(self):
        term = "UniqueSearchTerm"
        manuscript = Manuscript.objects.create(title=f"{term} paper")
        image = get_image_model().objects.create(
            title=f"{term} figure",
            file=get_test_image_file(),
        )
        document = Document(title=f"{term}.docx")
        document.file.save(f"{term}.docx", ContentFile(b"docx"), save=True)
        article_type = ArticleType.objects.create(
            code="unique-search-term",
            name=f"{term} catalog",
            sort_order=99,
        )
        reference = Reference.objects.create(
            mixed_citation=f"{term}, J. Fake Journal. 2024."
        )
        package = Document(title=f"{term} validation.zip")
        package.file.save(f"{term}-validation.zip", ContentFile(b"zip"), save=True)
        validation = SPSPackageValidation.objects.create(package_document=package)
        root = Page.get_first_root_node()
        page = HomePage(title=f"{term} homepage", slug="uniquesearchterm-home")
        root.add_child(instance=page)

        response = self.client.get(self.search_url, {"q": term})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, manuscript.title)
        self.assertContains(
            response,
            reverse(current_step_url_name(manuscript), args=[manuscript.pk]),
        )
        self.assertContains(response, image.title)
        self.assertContains(response, reverse("wagtailimages:edit", args=[image.pk]))
        self.assertContains(response, document.title)
        self.assertContains(response, reverse("wagtaildocs:edit", args=[document.pk]))
        self.assertContains(response, package.title)
        self.assertNotContains(response, article_type.name)
        self.assertNotContains(
            response,
            reverse(
                "wagtailsnippets_manuscript_articletype:edit",
                args=[article_type.pk],
            ),
        )
        self.assertNotContains(response, reference.mixed_citation)
        self.assertNotContains(
            response,
            reverse("wagtailsnippets_reference_reference:edit", args=[reference.pk]),
        )
        self.assertNotContains(
            response,
            reverse(
                "wagtailsnippets_xml_manager_spspackagevalidation:edit",
                args=[validation.pk],
            ),
        )
        self.assertNotContains(response, page.title)
        self.assertNotContains(
            response, reverse("wagtailadmin_pages:edit", args=[page.id])
        )

    def test_unmatched_query_returns_empty_sections(self):
        Manuscript.objects.create(title="Other manuscript")
        response = self.client.get(self.search_url, {"q": "zzznomatch"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manuscripts (0)")
        self.assertContains(response, "Images (0)")
        self.assertContains(response, "Documents (0)")
        self.assertContains(response, "No manuscripts found.")
        self.assertContains(response, "No images found.")
        self.assertContains(response, "No documents found.")
        self.assertNotContains(response, "Other manuscript")

    def test_construct_search_keeps_only_scielo_search_area(self):
        request = RequestFactory().get("/admin/")
        request.user = self.user
        search_areas = admin_search_areas.search_items_for_request(request)
        self.assertEqual(search_areas[0].name, SCIELO_SEARCH_AREA_NAME)
        for fn in hooks.get_hooks("construct_search"):
            fn(request, search_areas)
        self.assertEqual(
            [area.name for area in search_areas],
            [SCIELO_SEARCH_AREA_NAME],
        )

    def test_home_sidebar_search_module_uses_scielo_search(self):
        response = self.client.get(reverse("wagtailadmin_home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn(self.search_url, html)
        self.assertNotIn(reverse("wagtailadmin_pages:search"), html)

import io
import json
import re
import zipfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from front.utils import extract_text_from_docx
from manuscript.journeys import SAMPLES_DIR


class JourneyMenuTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="editor", email="editor@example.com", password="secret"
        )
        self.client.force_login(user)

    def test_menu_lists_five_numbered_journeys(self):
        response = self.client.get(reverse("wagtailadmin_home"))
        html = response.content.decode()
        match = re.search(
            r'<script id="wagtail-sidebar-props" '
            r'type="application/json">(.*?)</script>',
            html,
        )
        payload = json.loads(match.group(1))
        main_items = payload["modules"][2]["_args"][0]
        main_names = [item["_args"][0]["name"] for item in main_items]
        journeys = next(
            item for item in main_items if item["_args"][0]["name"] == "journeys"
        )
        children = journeys["_args"][1]
        child_names = [child["_args"][0]["name"] for child in children]
        child_labels = [child["_args"][0]["label"] for child in children]
        self.assertEqual(
            child_names,
            [
                "journey-complete",
                "journey-findings",
                "journey-references",
                "journey-manual",
                "journey-complex",
            ],
        )
        self.assertEqual(
            child_labels,
            ["Exemplo 1", "Exemplo 2", "Exemplo 3", "Exemplo 4", "Exemplo 5"],
        )
        self.assertEqual(journeys["_args"][0]["label"], "Exemplos de marcação")
        self.assertEqual(main_names[-1], "journeys")
        self.assertGreater(main_names.index("journeys"), main_names.index("documents"))

    def test_index_lists_journeys_without_create_button(self):
        response = self.client.get(reverse("manuscript_journeys"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Exemplo 1")
        self.assertContains(response, "Exemplo 5")
        self.assertContains(response, "Artigo completo")
        self.assertContains(response, "Artigo com erros na validação")
        self.assertContains(response, "sem a data Accepted")
        self.assertNotContains(response, "três falhas plantadas")
        self.assertNotContains(response, "figura 3 sem legenda")
        self.assertContains(response, "Equações, tabelas e imagens")
        self.assertContains(response, "Abrir exemplo")
        self.assertNotContains(response, "Criar manuscrito")
        self.assertContains(
            response, reverse("manuscript_journey_detail", args=["complete"])
        )
        self.assertContains(
            response, reverse("manuscript_journey_detail", args=["complex"])
        )

    def test_detail_shows_only_that_journey_documents(self):
        response = self.client.get(
            reverse("manuscript_journey_detail", args=["complete"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Exemplo 1")
        self.assertContains(response, "Artigo completo")
        self.assertContains(response, "ric-9999-0001-without-erro.docx")
        self.assertContains(response, "ric-9999-0001-without-erro.xml")
        self.assertContains(response, "ric-9999-0001-without-erro-sps.zip")
        self.assertContains(response, "Gabarito XML SPS")
        self.assertContains(response, "Gabarito pacote SPS")
        self.assertContains(
            response,
            "imagens/ric-9999-0001-without-erro-gf01.png",
        )
        self.assertContains(response, "Documentos deste exemplo")
        self.assertContains(response, "ric-9999-0001-without-erro.zip")
        self.assertContains(response, "Pacote com todos os arquivos")
        self.assertContains(
            response, reverse("manuscript_journey_zip", args=["complete"])
        )
        self.assertNotContains(response, "ric-9999-0001-with-erro.docx")
        self.assertNotContains(response, "ric-9999-0001-referencias.docx")
        self.assertNotContains(response, "ric-9999-0001-manual-front.txt")
        self.assertNotContains(response, "ric-9999-0001-complexo.docx")
        self.assertNotContains(response, "Criar manuscrito")

        complex_page = self.client.get(
            reverse("manuscript_journey_detail", args=["complex"])
        )
        self.assertEqual(complex_page.status_code, 200)
        self.assertContains(complex_page, "Exemplo 5")
        self.assertContains(complex_page, "Equações, tabelas e imagens")
        self.assertContains(
            complex_page,
            "DOCX com cinco equações tipográficas, quatro tabelas densas e "
            "quatro figuras, para treinar a marcação de conteúdo complexo.",
        )
        self.assertContains(complex_page, "ric-9999-0001-complexo.docx")
        self.assertContains(complex_page, "ric-9999-0001-complexo.xml")
        self.assertContains(complex_page, "ric-9999-0001-complexo-sps.zip")
        self.assertContains(complex_page, "Gabarito XML SPS")
        self.assertContains(complex_page, "ric-9999-0001-complexo.zip")
        self.assertContains(complex_page, "imagens/ric-9999-0001-complexo-gf01.png")
        self.assertNotContains(complex_page, "ric-9999-0001-without-erro.docx")
        self.assertNotContains(complex_page, "Criar manuscrito")
        html = complex_page.content.decode()
        summary_at = html.index(
            "DOCX com cinco equações tipográficas, quatro tabelas densas e "
            "quatro figuras, para treinar a marcação de conteúdo complexo."
        )
        zip_at = html.index("ric-9999-0001-complexo.zip")
        self.assertLess(summary_at, zip_at)

    def test_zip_contains_only_that_journey_files(self):
        response = self.client.get(reverse("manuscript_journey_zip", args=["complete"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn(
            'filename="ric-9999-0001-without-erro.zip"',
            response["Content-Disposition"],
        )
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            names = set(archive.namelist())
        self.assertEqual(
            names,
            {
                "ric-9999-0001-without-erro.docx",
                "ric-9999-0001-without-erro.xml",
                "ric-9999-0001-without-erro-sps.zip",
                "imagens/ric-9999-0001-without-erro-gf01.png",
                "imagens/ric-9999-0001-without-erro-gf02.png",
                "imagens/ric-9999-0001-without-erro-gf03.png",
                "imagens/ric-9999-0001-without-erro-gf04.png",
                "imagens/ric-9999-0001-without-erro-gf05.png",
            },
        )

        complex_zip = self.client.get(
            reverse("manuscript_journey_zip", args=["complex"])
        )
        self.assertEqual(complex_zip.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(complex_zip.content)) as archive:
            names = set(archive.namelist())
        self.assertEqual(
            names,
            {
                "ric-9999-0001-complexo.docx",
                "ric-9999-0001-complexo.xml",
                "ric-9999-0001-complexo-sps.zip",
                "imagens/ric-9999-0001-complexo-gf01.png",
                "imagens/ric-9999-0001-complexo-gf02.png",
                "imagens/ric-9999-0001-complexo-gf03.png",
                "imagens/ric-9999-0001-complexo-gf04.png",
            },
        )

        findings = self.client.get(
            reverse("manuscript_journey_detail", args=["findings"])
        )
        self.assertContains(findings, "ric-9999-0001-with-erro.xml")
        self.assertContains(findings, "ric-9999-0001-with-erro-sps.zip")
        self.assertContains(findings, "Artigo com erros na validação")
        self.assertContains(findings, "sem a data Accepted")
        self.assertNotContains(findings, "três falhas plantadas")
        self.assertNotContains(findings, "figura 3 sem legenda")
        self.assertNotContains(findings, "referência 17")
        references = self.client.get(
            reverse("manuscript_journey_detail", args=["references"])
        )
        self.assertContains(references, "ric-9999-0001-referencias.xml")
        self.assertContains(references, "ric-9999-0001-referencias-sps.zip")
        manual = self.client.get(reverse("manuscript_journey_detail", args=["manual"]))
        self.assertContains(manual, "ric-9999-0001-manual.xml")
        self.assertContains(manual, "ric-9999-0001-manual-sps.zip")

    def test_sample_download_returns_the_file(self):
        url = reverse(
            "manuscript_journey_sample",
            kwargs={"name": "ric-9999-0001-without-erro.docx"},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            response["Content-Type"],
        )
        self.assertTrue(response["Content-Disposition"].startswith("attachment;"))
        body = b"".join(response.streaming_content)
        self.assertTrue(body.startswith(b"PK"))

        xml_url = reverse(
            "manuscript_journey_sample",
            kwargs={"name": "ric-9999-0001-without-erro.xml"},
        )
        xml_response = self.client.get(xml_url)
        self.assertEqual(xml_response.status_code, 200)
        self.assertIn("application/xml", xml_response["Content-Type"])
        xml_body = b"".join(xml_response.streaming_content)
        self.assertTrue(
            xml_body.lstrip().startswith(b"<?xml") or xml_body.lstrip().startswith(b"<")
        )

        sps_url = reverse(
            "manuscript_journey_sample",
            kwargs={"name": "ric-9999-0001-without-erro-sps.zip"},
        )
        sps_response = self.client.get(sps_url)
        self.assertEqual(sps_response.status_code, 200)
        self.assertEqual(sps_response["Content-Type"], "application/zip")
        sps_body = b"".join(sps_response.streaming_content)
        self.assertTrue(sps_body.startswith(b"PK"))

    def test_findings_docx_has_credit_roles_and_no_accepted(self):
        findings = extract_text_from_docx(
            SAMPLES_DIR / "ric-9999-0001-with-erro.docx"
        )
        complete = extract_text_from_docx(
            SAMPLES_DIR / "ric-9999-0001-without-erro.docx"
        )
        for text in (findings, complete):
            self.assertIn("Author Contributions", text)
            self.assertIn("Lina Varejão: conceptualization", text)
            self.assertIn("Ivo Candeia: writing review and editing", text)
        self.assertNotIn("Accepted:", findings)
        self.assertIn("Accepted: 3 October 2024", complete)

    def test_unknown_sample_is_not_served(self):
        url = reverse(
            "manuscript_journey_sample",
            kwargs={"name": "imagens/../ric-9999-0001-without-erro.docx"},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class JourneyPermissionTests(TestCase):
    def test_viewer_can_open_journeys_and_download(self):
        user = get_user_model().objects.create_user(
            username="viewer", email="viewer@example.com", password="secret"
        )
        user.user_permissions.add(
            Permission.objects.get(codename="access_admin"),
        )
        self.client.force_login(user)
        page = self.client.get(reverse("manuscript_journeys"))
        self.assertEqual(page.status_code, 200)
        detail = self.client.get(reverse("manuscript_journey_detail", args=["complex"]))
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "Criar manuscrito")
        download = self.client.get(
            reverse(
                "manuscript_journey_sample",
                kwargs={"name": "ric-9999-0001-complexo.docx"},
            )
        )
        self.assertEqual(download.status_code, 200)

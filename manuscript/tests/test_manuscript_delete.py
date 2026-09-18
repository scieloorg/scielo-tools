import io
import os
import posixpath
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from wagtail.documents.models import Document

from manuscript.models import (
    Manuscript,
    ManuscriptFigureFile,
    ManuscriptPublication,
    ManuscriptReference,
)
from xml_manager.models import SPSPackageValidation, SPSPackageValidationStatus


def _make_document(title, content=b"data"):
    document = Document(title=title)
    document.file.save(title, ContentFile(content), save=True)
    return document


def _make_zip_document(title="pkg.zip"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("article.xml", b"<article/>")
    buffer.seek(0)
    return _make_document(title, buffer.read())


class ManuscriptDeleteCleanupTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="editor",
            email="editor@example.com",
            password="secret",
        )

    def _create_full_manuscript(self, title="To delete"):
        source = _make_document("source.docx", b"docx-bytes")
        package = _make_zip_document("package.zip")
        csv_doc = _make_document("report.validation.csv", b"a,b\n")
        exc_doc = _make_document("report.exceptions.json", b"{}")
        validation = SPSPackageValidation.objects.create(
            package_document=package,
            validation_document=csv_doc,
            exceptions_document=exc_doc,
            zip_size_bytes=package.file.size,
            status=SPSPackageValidationStatus.DONE,
        )
        manuscript = Manuscript.objects.create(
            title=title,
            source_document=source,
            sps_package=package,
            validation=validation,
            creator=self.user,
        )
        figure = ManuscriptFigureFile(
            manuscript=manuscript,
            number=1,
            href="fig-1.jpg",
            original_name="fig-1.jpg",
            sort_order=1,
        )
        figure.file.save("fig-1.jpg", ContentFile(b"jpeg-bytes"), save=True)
        ManuscriptReference.objects.create(
            manuscript=manuscript,
            mixed_citation="Author A. Article.",
            sort_order=0,
        )
        ManuscriptPublication.objects.create(
            manuscript=manuscript,
            external_id="ext-1",
            status="pending",
        )
        return {
            "manuscript": manuscript,
            "source": source,
            "package": package,
            "csv_doc": csv_doc,
            "exc_doc": exc_doc,
            "validation": validation,
            "figure": figure,
            "figure_path": figure.file.path,
            "source_path": source.file.path,
            "package_path": package.file.path,
            "csv_path": csv_doc.file.path,
            "exc_path": exc_doc.file.path,
        }

    def _assert_related_gone(self, payload):
        manuscript = payload["manuscript"]
        self.assertFalse(Manuscript.objects.filter(pk=manuscript.pk).exists())
        self.assertFalse(
            ManuscriptFigureFile.objects.filter(manuscript_id=manuscript.pk).exists()
        )
        self.assertFalse(
            ManuscriptReference.objects.filter(manuscript_id=manuscript.pk).exists()
        )
        self.assertFalse(
            ManuscriptPublication.objects.filter(manuscript_id=manuscript.pk).exists()
        )
        self.assertFalse(
            SPSPackageValidation.objects.filter(pk=payload["validation"].pk).exists()
        )
        self.assertFalse(
            Document.objects.filter(
                pk__in=[
                    payload["source"].pk,
                    payload["package"].pk,
                    payload["csv_doc"].pk,
                    payload["exc_doc"].pk,
                ]
            ).exists()
        )
        for path in (
            payload["figure_path"],
            payload["source_path"],
            payload["package_path"],
            payload["csv_path"],
            payload["exc_path"],
        ):
            self.assertFalse(os.path.exists(path))

    def test_instance_delete_removes_related_records_and_files(self):
        payload = self._create_full_manuscript()
        payload["manuscript"].delete()
        self._assert_related_gone(payload)

    def test_queryset_delete_removes_related_records_and_files(self):
        payload = self._create_full_manuscript()
        Manuscript.objects.filter(pk=payload["manuscript"].pk).delete()
        self._assert_related_gone(payload)

    def test_admin_delete_removes_related_records_and_files(self):
        payload = self._create_full_manuscript()
        self.client.force_login(self.user)
        url = reverse(
            "wagtailsnippets_manuscript_manuscript:delete",
            args=[payload["manuscript"].pk],
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self._assert_related_gone(payload)

    def test_shared_source_document_is_kept_until_last_manuscript(self):
        source = _make_document("shared.docx", b"shared")
        first = Manuscript.objects.create(title="First", source_document=source)
        second = Manuscript.objects.create(title="Second", source_document=source)
        source_path = source.file.path

        first.delete()

        self.assertTrue(Document.objects.filter(pk=source.pk).exists())
        self.assertTrue(os.path.exists(source_path))
        self.assertTrue(Manuscript.objects.filter(pk=second.pk).exists())

        second.delete()

        self.assertFalse(Document.objects.filter(pk=source.pk).exists())
        self.assertFalse(os.path.exists(source_path))

    def test_remove_all_manuscript_command_cleans_related(self):
        payload = self._create_full_manuscript()
        call_command("remove_all_manuscript", no_input=True)
        self._assert_related_gone(payload)

    def test_delete_removes_replaced_package_files_on_disk(self):
        package = _make_zip_document("pkg.zip")
        package_path = package.file.path
        leftover_name = posixpath.join(
            posixpath.dirname(package.file.name), "pkg_abc1234.zip"
        )
        leftover_path = package.file.storage.path(leftover_name)
        package.file.storage.save(leftover_name, ContentFile(b"old-zip"))
        csv_doc = _make_document("pkg.validation.csv", b"a,b\n")
        csv_path = csv_doc.file.path
        csv_leftover_name = posixpath.join(
            posixpath.dirname(csv_doc.file.name), "pkg_abc1234.validation.csv"
        )
        csv_leftover_path = csv_doc.file.storage.path(csv_leftover_name)
        csv_doc.file.storage.save(csv_leftover_name, ContentFile(b"old-csv"))
        validation = SPSPackageValidation.objects.create(
            package_document=package,
            validation_document=csv_doc,
            zip_size_bytes=package.file.size,
            status=SPSPackageValidationStatus.DONE,
        )
        manuscript = Manuscript.objects.create(
            title="Pkg leftovers",
            sps_package=package,
            validation=validation,
            creator=self.user,
        )

        manuscript.delete()

        for path in (package_path, leftover_path, csv_path, csv_leftover_path):
            self.assertFalse(os.path.exists(path))

    def test_delete_keeps_other_document_in_same_name_family(self):
        first = _make_zip_document("alpha.zip")
        second = Document(title="alpha.zip")
        second.file.save("alpha.zip", ContentFile(b"other-package"), save=True)
        first_ms = Manuscript.objects.create(
            title="First alpha", sps_package=first, creator=self.user
        )
        second_ms = Manuscript.objects.create(
            title="Second alpha", sps_package=second, creator=self.user
        )
        second_path = second.file.path

        first_ms.delete()

        self.assertTrue(Document.objects.filter(pk=second.pk).exists())
        self.assertTrue(os.path.exists(second_path))
        self.assertTrue(Manuscript.objects.filter(pk=second_ms.pk).exists())

        second_ms.delete()

        self.assertFalse(Document.objects.filter(pk=second.pk).exists())
        self.assertFalse(os.path.exists(second_path))

    def test_delete_removes_replaced_figure_files_on_disk(self):
        manuscript = Manuscript.objects.create(title="Figs", creator=self.user)
        figure = ManuscriptFigureFile(
            manuscript=manuscript,
            number=1,
            href="fig-1.jpg",
            original_name="fig-1.jpg",
            sort_order=1,
        )
        figure.file.save("fig-1.jpg", ContentFile(b"jpeg-v2"), save=True)
        leftover_name = posixpath.join(
            posixpath.dirname(figure.file.name), "fig-1_abc1234.jpg"
        )
        leftover_path = figure.file.storage.path(leftover_name)
        figure.file.storage.save(leftover_name, ContentFile(b"jpeg-v1"))
        figure_path = figure.file.path

        manuscript.delete()

        self.assertFalse(os.path.exists(figure_path))
        self.assertFalse(os.path.exists(leftover_path))

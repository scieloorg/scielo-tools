import csv
import io
import os
import tempfile
import zipfile
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.utils import timezone
from wagtail.documents.models import Document

from xml_manager.forms import SPSPackageValidationForm
from xml_manager.models import SPSPackageValidation, SPSPackageValidationStatus
from xml_manager.services import run_sps_package_validation
from xml_manager.utils import FIELDNAMES, validate_zip, write_csv, write_exceptions_json
from xml_manager.views import revalidate_sps_package_pk

User = get_user_model()


def make_minimal_sps_zip(xml_name="article.xml", xml_body=b"<article/>"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(xml_name, xml_body)
    buffer.seek(0)
    return buffer.read()


def make_package_document(title="pkg.zip"):
    upload = SimpleUploadedFile(
        title,
        make_minimal_sps_zip(),
        content_type="application/zip",
    )
    document = Document(title=title)
    document.file.save(title, upload, save=True)
    return document, upload.size


class SPSPackageValidationFormTests(TestCase):
    def test_create_requires_zip(self):
        form = SPSPackageValidationForm(data={})
        self.assertFalse(form.is_valid())

    def test_rejects_non_zip_extension(self):
        upload = SimpleUploadedFile("pkg.txt", b"data", content_type="text/plain")
        form = SPSPackageValidationForm(
            files={"zip_upload": upload},
            data={},
        )
        self.assertFalse(form.is_valid())

    def test_accepts_zip_upload(self):
        upload = SimpleUploadedFile(
            "pkg.zip",
            make_minimal_sps_zip(),
            content_type="application/zip",
        )
        form = SPSPackageValidationForm(
            files={"zip_upload": upload},
            data={},
        )
        self.assertTrue(form.is_valid())


class SPSPackageValidationDeleteTests(TestCase):
    def test_delete_removes_all_wagtail_documents(self):
        package, zip_size = make_package_document()
        csv_doc = Document(title="report.validation.csv")
        csv_doc.file.save(
            "report.validation.csv",
            SimpleUploadedFile("report.validation.csv", b"a,b\n"),
            save=True,
        )
        exc_doc = Document(title="report.exceptions.json")
        exc_doc.file.save(
            "report.exceptions.json",
            SimpleUploadedFile("report.exceptions.json", b"{}"),
            save=True,
        )
        document_ids = {package.pk, csv_doc.pk, exc_doc.pk}

        validation = SPSPackageValidation.objects.create(
            package_document=package,
            validation_document=csv_doc,
            exceptions_document=exc_doc,
            zip_size_bytes=zip_size,
        )
        package_path = package.file.path
        csv_path = csv_doc.file.path
        exc_path = exc_doc.file.path
        validation.delete()

        self.assertFalse(SPSPackageValidation.objects.filter(pk=validation.pk).exists())
        self.assertFalse(Document.objects.filter(pk__in=document_ids).exists())
        self.assertFalse(os.path.exists(package_path))
        self.assertFalse(os.path.exists(csv_path))
        self.assertFalse(os.path.exists(exc_path))

    def test_delete_package_only_removes_package_document(self):
        package, zip_size = make_package_document()
        validation = SPSPackageValidation.objects.create(
            package_document=package,
            zip_size_bytes=zip_size,
        )
        package_id = package.pk
        package_path = package.file.path

        validation.delete()

        self.assertFalse(Document.objects.filter(pk=package_id).exists())
        self.assertFalse(os.path.exists(package_path))

    def test_delete_does_not_raise_recursion_error(self):
        package, zip_size = make_package_document()
        csv_doc = Document(title="report.validation.csv")
        csv_doc.file.save(
            "report.validation.csv",
            SimpleUploadedFile("report.validation.csv", b"a,b\n"),
            save=True,
        )
        exc_doc = Document(title="report.exceptions.json")
        exc_doc.file.save(
            "report.exceptions.json",
            SimpleUploadedFile("report.exceptions.json", b"{}"),
            save=True,
        )
        validation = SPSPackageValidation.objects.create(
            package_document=package,
            validation_document=csv_doc,
            exceptions_document=exc_doc,
            zip_size_bytes=zip_size,
            status=SPSPackageValidationStatus.DONE,
        )
        validation.delete()

    def test_queryset_delete_removes_linked_documents(self):
        package, zip_size = make_package_document()
        csv_doc = Document(title="report.validation.csv")
        csv_doc.file.save(
            "report.validation.csv",
            SimpleUploadedFile("report.validation.csv", b"a,b\n"),
            save=True,
        )
        validation = SPSPackageValidation.objects.create(
            package_document=package,
            validation_document=csv_doc,
            zip_size_bytes=zip_size,
        )
        document_ids = {package.pk, csv_doc.pk}
        validation_pk = validation.pk

        SPSPackageValidation.objects.filter(pk=validation_pk).delete()

        self.assertFalse(SPSPackageValidation.objects.filter(pk=validation_pk).exists())
        self.assertFalse(Document.objects.filter(pk__in=document_ids).exists())


def _request_for_user(user):
    request = RequestFactory().get("/admin/xml-manager/revalidate-sps/1/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


class SPSPackageValidationRevalidateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="staff", password="secret", is_staff=True
        )
        self.package, self.zip_size = make_package_document()
        self.validation = SPSPackageValidation.objects.create(
            package_document=self.package,
            zip_size_bytes=self.zip_size,
            status=SPSPackageValidationStatus.DONE,
            validated_by=self.user,
            validated_at=timezone.now(),
            error_message="old error",
        )

    def test_revalidate_requires_staff(self):
        request = _request_for_user(
            User.objects.create_user(username="regular", password="secret")
        )
        response = revalidate_sps_package_pk(request, pk=self.validation.pk)
        self.assertEqual(response.status_code, 302)

    def test_revalidate_returns_404_for_missing_validation(self):
        request = _request_for_user(self.user)
        with self.assertRaises(Http404):
            revalidate_sps_package_pk(request, pk=99999)

    def test_revalidate_runs_validation(self):
        with patch("xml_manager.views.run_sps_package_validation") as mock_run:
            request = _request_for_user(self.user)
            revalidate_sps_package_pk(request, pk=self.validation.pk)
            mock_run.assert_called_once_with(self.validation.pk)


def _mock_validation_results(items):
    if items is None:
        return iter([])
    results = []
    for item in items:
        if not item:
            continue
        row = dict(item)
        row.setdefault("group", "test-group")
        results.append(row)
    return iter(results)


def _mock_xml_with_pre(mock_xmltree=None):
    mock_xml = MagicMock()
    mock_xml.xmltree = mock_xmltree or MagicMock()
    return mock_xml


class ValidateZipTests(TestCase):
    def _patch_packtools(self, items):
        patcher_xmlwithpre = patch(
            "xml_manager.utils.XMLWithPre.create",
            return_value=iter([_mock_xml_with_pre()]),
        )
        patcher_validator = patch(
            "xml_manager.utils.get_validation_results",
            return_value=_mock_validation_results(items),
        )
        patcher_journal = patch(
            "xml_manager.utils._extract_journal_data",
            return_value={},
        )
        return patcher_xmlwithpre, patcher_validator, patcher_journal

    def test_returns_list_of_dicts(self):
        item = {
            "title": "t",
            "parent": "article",
            "parent_id": None,
            "parent_article_type": "research-article",
            "item": "article-id",
            "sub_item": None,
            "validation_type": "format",
            "response": "ERROR",
            "expected_value": "doi",
            "got_value": None,
            "advice": "add doi",
        }
        p1, p2, p3 = self._patch_packtools([item])
        with p1, p2, p3:
            rows, exceptions = validate_zip("fake.zip")
        self.assertIsInstance(rows, list)
        self.assertEqual(len(rows), 1)
        self.assertEqual(exceptions, [])

    def test_result_has_expected_keys(self):
        item = {
            "title": "t",
            "parent": "article",
            "parent_id": None,
            "parent_article_type": "research-article",
            "item": "article-id",
            "sub_item": "pub-id-type",
            "validation_type": "format",
            "response": "ERROR",
            "expected_value": "doi",
            "got_value": None,
            "advice": "add doi",
        }
        p1, p2, p3 = self._patch_packtools([item])
        with p1, p2, p3:
            rows, _exceptions = validate_zip("fake.zip")
        for key in FIELDNAMES:
            self.assertIn(key, rows[0])

    def test_attribute_concatenates_item_and_sub_item(self):
        item = {
            "title": None,
            "parent": None,
            "parent_id": None,
            "parent_article_type": None,
            "item": "foo",
            "sub_item": "bar",
            "validation_type": None,
            "response": "ERROR",
            "expected_value": None,
            "got_value": None,
            "advice": None,
        }
        p1, p2, p3 = self._patch_packtools([item])
        with p1, p2, p3:
            rows, _exceptions = validate_zip("fake.zip")
        self.assertEqual(rows[0]["attribute"], "foo/bar")

    def test_attribute_omits_empty_sub_item(self):
        item = {
            "title": None,
            "parent": None,
            "parent_id": None,
            "parent_article_type": None,
            "item": "foo",
            "sub_item": None,
            "validation_type": None,
            "response": "ERROR",
            "expected_value": None,
            "got_value": None,
            "advice": None,
        }
        p1, p2, p3 = self._patch_packtools([item])
        with p1, p2, p3:
            rows, _exceptions = validate_zip("fake.zip")
        self.assertEqual(rows[0]["attribute"], "foo")

    def test_collects_exception_items(self):
        exception_item = {
            "response": "exception",
            "group": "article-id",
            "error": "boom",
            "type": "ValueError",
        }
        p1, p2, p3 = self._patch_packtools([exception_item])
        with p1, p2, p3:
            rows, exceptions = validate_zip("fake.zip")
        self.assertEqual(rows, [])
        self.assertEqual(len(exceptions), 1)
        self.assertEqual(exceptions[0]["response"], "exception")

    def test_handles_none_items_in_group(self):
        p1, p2, p3 = self._patch_packtools([None, None])
        with p1, p2, p3:
            rows, exceptions = validate_zip("fake.zip")
        self.assertEqual(rows, [])
        self.assertEqual(exceptions, [])

    def test_handles_none_items_list(self):
        p1, p2, p3 = self._patch_packtools(None)
        with p1, p2, p3:
            rows, exceptions = validate_zip("fake.zip")
        self.assertEqual(rows, [])
        self.assertEqual(exceptions, [])


class WriteExceptionsJsonTests(TestCase):
    def test_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "out.exceptions.json")
            write_exceptions_json([], path)
            self.assertTrue(os.path.exists(path))

    def test_writes_jsonl_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "out.exceptions.json")
            write_exceptions_json(
                [{"response": "exception", "group": "g", "error": "e"}],
                path,
            )
            with open(path, encoding="utf-8") as fp:
                content = fp.read()
            self.assertIn('"response": "exception"', content)

    def test_returns_output_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "out.exceptions.json")
            returned = write_exceptions_json([], path)
            self.assertEqual(returned, path)


class WriteCsvTests(TestCase):
    def test_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "out.csv")
            write_csv([], path)
            self.assertTrue(os.path.exists(path))

    def test_has_correct_header(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "out.csv")
            write_csv([], path)
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames, FIELDNAMES)

    def test_returns_output_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "out.csv")
            returned = write_csv([], path)
            self.assertEqual(returned, path)


class RunSPSPackageValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="staff", password="secret", is_staff=True
        )
        self.package, self.zip_size = make_package_document()
        self.validation = SPSPackageValidation.objects.create(
            package_document=self.package,
            zip_size_bytes=self.zip_size,
            validated_by=self.user,
        )

    def _run(self, rows=None, exceptions=None):
        with patch(
            "xml_manager.services.utils.validate_zip",
            return_value=(rows or [], exceptions or []),
        ):
            run_sps_package_validation(self.validation.pk)

    def test_status_transitions_to_done(self):
        self._run()
        self.validation.refresh_from_db()
        self.assertEqual(self.validation.status, SPSPackageValidationStatus.DONE)

    def test_validation_document_is_created(self):
        self._run()
        self.validation.refresh_from_db()
        self.assertIsNotNone(self.validation.validation_document)

    def test_exceptions_document_is_created(self):
        self._run(exceptions=[{"response": "exception", "group": "g", "error": "e"}])
        self.validation.refresh_from_db()
        self.assertIsNotNone(self.validation.exceptions_document)

    def test_existing_exceptions_document_replaced(self):
        old_doc = Document(title="old.exceptions.json")
        old_doc.file.save(
            "old.exceptions.json",
            SimpleUploadedFile("old.exceptions.json", b"{}"),
            save=True,
        )
        old_doc_pk = old_doc.pk
        self.validation.exceptions_document = old_doc
        self.validation.save()

        self._run()
        self.validation.refresh_from_db()

        self.assertTrue(Document.objects.filter(pk=old_doc_pk).exists())
        self.assertEqual(self.validation.exceptions_document.pk, old_doc_pk)
        self.assertTrue(os.path.exists(self.validation.exceptions_document.file.path))

    def test_validated_at_is_set(self):
        self._run()
        self.validation.refresh_from_db()
        self.assertIsNotNone(self.validation.validated_at)

    def test_error_message_cleared_on_done(self):
        self.validation.error_message = "old error"
        self.validation.save()
        self._run()
        self.validation.refresh_from_db()
        self.assertEqual(self.validation.error_message, "")

    def test_status_transitions_to_error_on_failure(self):
        with patch(
            "xml_manager.services.utils.validate_zip", side_effect=Exception("boom")
        ):
            run_sps_package_validation(self.validation.pk)
        self.validation.refresh_from_db()
        self.assertEqual(self.validation.status, SPSPackageValidationStatus.ERROR)
        self.assertEqual(self.validation.error_message, "boom")

    def test_existing_validation_document_replaced(self):
        old_doc = Document(title="old.csv")
        old_doc.file.save(
            "old.csv",
            SimpleUploadedFile("old.csv", b"a,b\n"),
            save=True,
        )
        old_doc_pk = old_doc.pk
        self.validation.validation_document = old_doc
        self.validation.save()

        self._run()
        self.validation.refresh_from_db()

        self.assertTrue(Document.objects.filter(pk=old_doc_pk).exists())
        self.assertEqual(self.validation.validation_document.pk, old_doc_pk)
        self.assertTrue(os.path.exists(self.validation.validation_document.file.path))

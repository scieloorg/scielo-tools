import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from body.data_utils import get_body_xml
from front.data_utils import get_front_xml
from manuscript.models import Manuscript, ManuscriptReference, ManuscriptStatus
from manuscript.services.validation import run_manuscript_validation
from xml_manager.models import SPSPackageValidation, SPSPackageValidationStatus

User = get_user_model()


class RunManuscriptValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="editor", password="secret")
        self.manuscript = Manuscript.objects.create(
            title="Validation test",
            status=ManuscriptStatus.ASSEMBLED,
            creator=self.user,
            front_marked_xml=get_front_xml(
                {
                    "journal": {
                        "journal_ids": [{"type": "publisher-id", "value": "scie"}],
                        "issns": [{"pub_type": "epub", "value": "0124-4567"}],
                    },
                    "titles": [
                        {"kind": "main", "text": "Validation title", "language": "en"}
                    ],
                    "volume": "10",
                    "issue": "3",
                    "fpage": "365",
                }
            ),
            body_marked_xml=get_body_xml(
                {
                    "sections": [
                        {
                            "title": "Intro",
                            "content": [{"type": "p", "text": "Paragraph."}],
                            "sections": [],
                        }
                    ]
                }
            ),
        )
        ManuscriptReference.objects.create(
            manuscript=self.manuscript,
            mixed_citation="Author A. Article.",
            marked={"reftype": "journal", "source": "Journal", "date": "2024"},
            marked_xml=(
                '<element-citation publication-type="journal">'
                "<source>Journal</source><year>2024</year>"
                "</element-citation>"
            ),
            sort_order=0,
        )

    def _run(self):
        with patch(
            "xml_manager.services.utils.validate_zip",
            return_value=([], []),
        ):
            return run_manuscript_validation(self.manuscript, user=self.user)

    def test_first_validation_creates_record(self):
        validation = self._run()
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.validation_id, validation.pk)
        self.assertEqual(validation.status, SPSPackageValidationStatus.DONE)
        self.assertEqual(SPSPackageValidation.objects.count(), 1)

    def test_revalidation_reuses_existing_record(self):
        first = self._run()
        second = self._run()
        self.manuscript.refresh_from_db()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SPSPackageValidation.objects.count(), 1)
        self.assertEqual(self.manuscript.validation_id, first.pk)
        self.assertEqual(second.status, SPSPackageValidationStatus.DONE)

    def test_revalidation_after_workflow_reopen(self):
        first = self._run()
        self.manuscript.validation = None
        self.manuscript.save(update_fields=["validation", "updated"])
        second = self._run()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SPSPackageValidation.objects.count(), 1)

    def test_revalidation_keeps_edited_assembled_xml(self):
        self._run()
        edited = (
            "<article><front><journal-meta>"
            '<journal-id journal-id-type="publisher-id">scie</journal-id>'
            '<issn pub-type="epub">0124-4567</issn>'
            "</journal-meta><article-meta>"
            "<volume>10</volume><issue>3</issue><fpage>365</fpage>"
            "<title-group><article-title>"
            "Edited before revalidation</article-title></title-group>"
            "</article-meta></front></article>"
        )
        self.manuscript.assembled_xml = edited
        self.manuscript.save(update_fields=["assembled_xml", "updated"])
        self._run()
        self.manuscript.refresh_from_db()
        self.assertEqual(self.manuscript.assembled_xml, edited)

    def test_revalidation_keeps_csv_file_on_disk(self):
        first = self._run()
        first_path = first.validation_document.file.path
        self.assertTrue(os.path.exists(first_path))
        second = self._run()
        second.refresh_from_db()
        self.assertEqual(first.validation_document_id, second.validation_document_id)
        self.assertTrue(os.path.exists(second.validation_document.file.path))

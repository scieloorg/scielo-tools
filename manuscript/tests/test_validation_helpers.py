from django.test import TestCase

from manuscript.services.validation import (
    group_validation_rows,
    group_validation_rows_by_response,
    read_validation_csv,
    response_for_validation_row,
)


class ValidationHelperTests(TestCase):
    def test_group_validation_rows(self):
        rows = [
            {"group": "front", "response": "ERROR"},
            {"group": "front", "response": "WARNING"},
            {"group": "body", "response": "ERROR"},
        ]
        grouped = group_validation_rows(rows)
        self.assertEqual(len(grouped["front"]), 2)
        self.assertEqual(len(grouped["body"]), 1)

    def test_response_for_validation_row(self):
        self.assertEqual(
            response_for_validation_row({"response": "critical"}), "CRITICAL"
        )
        self.assertEqual(response_for_validation_row({"response": "ERROR"}), "ERROR")
        self.assertEqual(response_for_validation_row({"response": "OK"}), None)
        self.assertEqual(response_for_validation_row({"response": "UNKNOWN"}), "ERROR")

    def test_group_validation_rows_by_response(self):
        rows = [
            {"group": "bibliographic strip", "response": "WARNING"},
            {"group": "reference", "response": "ERROR"},
            {"group": "sec", "response": "CRITICAL"},
        ]
        responses = group_validation_rows_by_response(rows)
        self.assertEqual(
            [item["response"] for item in responses],
            ["CRITICAL", "ERROR", "WARNING"],
        )
        self.assertEqual(responses[0]["rows"][0]["group"], "sec")
        self.assertEqual(responses[1]["rows"][0]["group"], "reference")

    def test_read_validation_csv_marks_missing_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from wagtail.documents.models import Document

        document = Document(title="gone.validation.csv")
        document.file.save(
            "gone.validation.csv",
            SimpleUploadedFile("gone.validation.csv", b"group,response\n"),
            save=True,
        )
        document.file.storage.delete(document.file.name)
        rows, unreadable = read_validation_csv(document)
        self.assertEqual(rows, [])
        self.assertTrue(unreadable)

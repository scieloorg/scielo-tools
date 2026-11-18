from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from xml_manager.utils import validate_zip

GABARITO_ZIP = (
    Path(settings.BASE_DIR)
    / "docs"
    / "guia"
    / "amostras"
    / "ric-9999-0001-without-erro-sps.zip"
)


class WithoutErroGabaritoTests(SimpleTestCase):
    def test_gabarito_sps_zip_has_no_critical_error_or_warning(self):
        self.assertTrue(GABARITO_ZIP.is_file(), GABARITO_ZIP)
        rows, exceptions = validate_zip(str(GABARITO_ZIP))
        self.assertEqual(exceptions, [])
        bad = [
            row
            for row in rows
            if (row.get("response") or "").upper() in {"CRITICAL", "ERROR", "WARNING"}
        ]
        self.assertEqual(
            bad,
            [],
            [
                (
                    row.get("response"),
                    row.get("group"),
                    row.get("title"),
                    row.get("advice"),
                )
                for row in bad[:20]
            ],
        )

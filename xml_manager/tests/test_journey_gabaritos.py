from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from xml_manager.utils import validate_zip

SAMPLES = Path(settings.BASE_DIR) / "docs" / "guia" / "amostras"

GABARITO_ZIPS = (
    "ric-9999-0001-without-erro-sps.zip",
    "ric-9999-0001-with-erro-sps.zip",
    "ric-9999-0001-referencias-sps.zip",
    "ric-9999-0001-manual-sps.zip",
    "ric-9999-0001-complexo-sps.zip",
)


class JourneyGabaritoTests(SimpleTestCase):
    def test_all_journey_gabarito_sps_zips_are_clean(self):
        for name in GABARITO_ZIPS:
            zip_path = SAMPLES / name
            with self.subTest(name=name):
                self.assertTrue(zip_path.is_file(), zip_path)
                rows, exceptions = validate_zip(str(zip_path))
                self.assertEqual(exceptions, [])
                bad = [
                    row
                    for row in rows
                    if (row.get("response") or "").upper()
                    in {"CRITICAL", "ERROR", "WARNING"}
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

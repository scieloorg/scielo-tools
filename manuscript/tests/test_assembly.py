from django.test import TestCase
from lxml import etree

from body.data_utils import get_body_xml
from front.data_utils import get_front_xml
from reference.data_utils import build_ref_list
from xml_manager.assembly import generate_xml_sps

MINIMAL_FRONT = get_front_xml(
    {
        "titles": [{"kind": "main", "text": "Sample title", "language": "en"}],
        "abstracts": [
            {"kind": "main", "title": "Abstract", "text": "Sample abstract."}
        ],
    }
)

MINIMAL_BODY = get_body_xml(
    {
        "sections": [
            {
                "title": "Introduction",
                "content": [{"type": "p", "text": "Body paragraph."}],
                "sections": [],
            }
        ]
    }
)

MINIMAL_BACK = build_ref_list(
    [
        {
            "mixed_citation": "Author A. Sample reference.",
            "data": (
                '<element-citation publication-type="journal">'
                '<person-group person-group-type="author">'
                "<name><surname>Author</surname></name>"
                "</person-group>"
                "<article-title>Sample</article-title>"
                "<source>Journal</source>"
                "<year>2024</year>"
                "</element-citation>"
            ),
        }
    ]
)


class GenerateXmlSpsTests(TestCase):
    def test_generate_xml_sps_builds_article(self):
        xml = generate_xml_sps(MINIMAL_FRONT, MINIMAL_BODY, MINIMAL_BACK)
        self.assertIn("<article", xml)
        self.assertIn("<front>", xml)
        self.assertIn("<body>", xml)
        self.assertIn("<back>", xml)
        self.assertIn("Sample title", xml)
        self.assertIn("Body paragraph.", xml)
        self.assertIn('specific-use="sps-1.10"', xml)

    def test_generate_xml_sps_uses_keyword_language_when_configured_lang_is_translation(self):
        front = get_front_xml(
            {
                "titles": [
                    {"kind": "main", "text": "English title"},
                    {
                        "kind": "translated",
                        "language": "pt",
                        "text": "Título em português",
                    },
                ],
                "keywords": [
                    {"language": "en", "keywords": ["Forest"]},
                    {"language": "pt", "keywords": ["Floresta"]},
                ],
                "abstracts": [
                    {"kind": "main", "title": "Abstract", "text": "English abstract."}
                ],
            }
        )
        xml = generate_xml_sps(
            front, MINIMAL_BODY, MINIMAL_BACK, language="pt"
        )
        root = etree.fromstring(xml.encode())
        self.assertEqual(
            root.get("{http://www.w3.org/XML/1998/namespace}lang"),
            "en",
        )

    def test_generate_xml_sps_keeps_original_language_when_translation_is_other(self):
        front = get_front_xml(
            {
                "titles": [
                    {"kind": "main", "text": "Título em português"},
                    {"kind": "translated", "language": "en", "text": "English title"},
                ],
                "keywords": [
                    {"language": "pt", "keywords": ["Floresta"]},
                    {"language": "en", "keywords": ["Forest"]},
                ],
            }
        )
        xml = generate_xml_sps(
            front, MINIMAL_BODY, MINIMAL_BACK, language="pt"
        )
        root = etree.fromstring(xml.encode())
        self.assertEqual(
            root.get("{http://www.w3.org/XML/1998/namespace}lang"),
            "pt",
        )

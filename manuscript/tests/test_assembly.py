from django.test import TestCase

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

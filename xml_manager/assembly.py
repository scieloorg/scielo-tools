from lxml import etree

XLINK_NS = "http://www.w3.org/1999/xlink"
MML_NS = "http://www.w3.org/1998/Math/MathML"
XML_NS = "http://www.w3.org/XML/1998/namespace"
XML_LANG = f"{{{XML_NS}}}lang"
JATS_DOCTYPE = (
    '<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Publishing DTD '
    'v1.1 20151215//EN" '
    '"https://jats.nlm.nih.gov/publishing/1.1/JATS-journalpublishing1.dtd">'
)


def parse_fragment(xml, expected_tags):
    if xml is None or not str(xml).strip():
        raise ValueError("Empty XML fragment")
    text = xml if isinstance(xml, str) else xml.decode("utf-8")
    try:
        root = etree.fromstring(text.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Invalid XML: {exc}") from exc
    tag = etree.QName(root).localname
    if tag not in expected_tags:
        names = " or ".join(f"<{name}>" for name in expected_tags)
        raise ValueError(f"Expected root {names}, got <{tag}>")
    return root


def generate_xml_sps(
    front_xml,
    body_xml,
    back_xml,
    article_type="research-article",
    language=None,
    specific_use="sps-1.10",
):
    front = parse_fragment(front_xml, ("front",))
    body = parse_fragment(body_xml, ("body",))
    back_root = parse_fragment(back_xml, ("ref-list", "back"))
    if etree.QName(back_root).localname == "back":
        back = back_root
    else:
        back = etree.Element("back")
        back.append(back_root)

    xml_lang = (language or "").strip()
    if not xml_lang:
        for abstract in front.findall(".//abstract"):
            value = (abstract.get(XML_LANG) or "").strip()
            if value:
                xml_lang = value
                break
    if not xml_lang:
        title = front.find(".//article-title")
        if title is not None:
            xml_lang = (title.get(XML_LANG) or "").strip()
    if not xml_lang:
        xml_lang = "en"

    article = etree.Element(
        "article",
        attrib={
            "article-type": article_type or "research-article",
            "dtd-version": "1.1",
            "specific-use": specific_use or "sps-1.10",
            XML_LANG: xml_lang,
        },
        nsmap={"mml": MML_NS, "xlink": XLINK_NS},
    )
    article.append(front)
    article.append(body)
    article.append(back)
    xml_bytes = etree.tostring(
        article,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
        doctype=JATS_DOCTYPE,
    )
    return xml_bytes.decode("utf-8")

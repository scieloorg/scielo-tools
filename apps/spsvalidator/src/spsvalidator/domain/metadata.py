from __future__ import annotations

from lxml import etree


def extract_article_snapshot(xml_content: bytes, xml_path: str) -> dict:
    tree = etree.fromstring(xml_content)
    title_nodes = tree.xpath(".//article-meta/title-group/article-title")
    title = " ".join(title_nodes[0].itertext()).strip() if title_nodes else ""
    doi = tree.xpath("string(.//article-id[@pub-id-type='doi'][1])").strip().lower()
    pid = (
        tree.xpath("string(.//article-id[@pub-id-type='publisher-id'][1])").strip()
        or tree.xpath("string(.//article-id[@pub-id-type='other'][1])").strip()
    )
    authors = []
    for contrib in tree.xpath(
        ".//article-meta/contrib-group/contrib[@contrib-type='author']"
    ):
        surname = contrib.xpath("string(./name/surname)").strip()
        given_names = contrib.xpath("string(./name/given-names)").strip()
        full_name = f"{given_names} {surname}".strip()
        if full_name:
            authors.append(full_name)
    return {
        "xml_path": xml_path,
        "title": title,
        "authors": authors,
        "authors_text": "; ".join(authors[:5]),
        "doi": doi,
        "pid": pid,
    }

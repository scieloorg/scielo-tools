from pathlib import Path

from spsvalidator.domain.metadata import extract_article_snapshot


def test_extract_article_snapshot_reads_title_and_authors():
    xml_path = (
        Path(__file__).resolve().parents[3] / "fixtures" / "xml" / "dias_2023.xml"
    )
    snapshot = extract_article_snapshot(xml_path.read_bytes(), "dias_2023.xml")
    assert snapshot["title"]
    assert "Differentiating diversity" in snapshot["title"]
    assert snapshot["authors"]
    assert "Carlos Henrique Saraiva DIAS" in snapshot["authors_text"]

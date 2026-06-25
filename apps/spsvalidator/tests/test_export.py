import csv
import io

from spsvalidator.domain.export import build_validation_csv


def test_build_validation_csv_includes_all_columns():
    rows = [
        {
            "group": "meta",
            "title": "Title check",
            "parent": "article.xml",
            "parent_id": "art1",
            "parent_article_type": "research-article",
            "item": "title",
            "sub_item": "",
            "attribute": "title",
            "validation_type": "value",
            "response": "ERROR",
            "expected_value": "x",
            "got_value": "y",
            "advice": "fix it",
        }
    ]
    content = build_validation_csv(rows)
    parsed = list(csv.DictReader(io.StringIO(content)))
    assert len(parsed) == 1
    assert parsed[0]["group"] == "meta"
    assert parsed[0]["response"] == "ERROR"
    assert parsed[0]["advice"] == "fix it"

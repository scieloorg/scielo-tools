import csv
import json

from packtools.sps.models.article_license import ArticleLicense
from packtools.sps.models.front_articlemeta_issue import ArticleMetaIssue
from packtools.sps.pid_provider.models.journal_meta import JournalID, Publisher, Title
from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre
from packtools.sps.validation.xml_validator import get_validation_results
from packtools.sps.validation.xml_validator_rules import get_default_rules

FIELDNAMES = [
    "group",
    "title",
    "parent",
    "parent_id",
    "parent_article_type",
    "item",
    "sub_item",
    "attribute",
    "validation_type",
    "response",
    "expected_value",
    "got_value",
    "advice",
]


def _extract_journal_data(xmltree):
    try:
        license_code = None
        for lic in ArticleLicense(xmltree).licenses:
            code = lic.get("code")
            if code:
                license_code = code
                break
        abbrev = Title(xmltree).abbreviated_journal_title
        if not abbrev:
            abbrev = xmltree.findtext(".//abbrev-journal-title")
        publishers = list(Publisher(xmltree).publishers_names or [])
        if not publishers:
            for name in xmltree.xpath(".//publisher-name/text()"):
                text = str(name or "").strip()
                if text:
                    publishers.append(text)
        meta_issue = ArticleMetaIssue(xmltree)
        issues = [
            {
                "volume": meta_issue.volume,
                "number": meta_issue.number,
                "supplement": meta_issue.suppl,
            }
        ]
        xml_lang = "{http://www.w3.org/XML/1998/namespace}lang"
        lang = xmltree.get(xml_lang) or "pt"
        subjects = [
            node.text.strip()
            for node in xmltree.xpath(
                './/subj-group[@subj-group-type="heading"]/subject'
            )
            if node.text and node.text.strip()
        ]
        toc_sections = {lang: subjects} if subjects else {}
        return {
            "abbrev_journal_title": abbrev,
            "publisher_name_list": publishers,
            "nlm_journal_title": JournalID(xmltree).nlm_ta,
            "license_code": license_code,
            "issues": issues,
            "toc_sections": toc_sections,
        }
    except Exception:
        return {}


def validate_zip(zip_path: str) -> tuple[list, list]:
    rows = []
    exceptions = []
    for xml_with_pre in XMLWithPre.create(path=zip_path):
        xmltree = xml_with_pre.xmltree
        rules = get_default_rules()
        rules["journal_data"] = _extract_journal_data(xmltree)
        inline_rules = dict(rules.get("inline_formula_rules") or {})
        inline_rules["absent_error_level"] = None
        rules["inline_formula_rules"] = inline_rules
        disp_rules = dict(rules.get("disp_formula_rules") or {})
        if "absent_error_level" in disp_rules:
            disp_rules["absent_error_level"] = None
        rules["disp_formula_rules"] = disp_rules
        app_rules = dict(rules.get("app_group_rules") or {})
        app_rules["app_existence_error_level"] = None
        rules["app_group_rules"] = app_rules
        for result in get_validation_results(xmltree, rules):
            if not result:
                continue
            if result.get("response") == "exception":
                exceptions.append(result)
                continue
            response = result.get("response")
            if response is None or str(response).upper() in ("", "OK", "NONE"):
                continue
            group = result.get("group", "")
            item = result.get("item") or ""
            sub_item = result.get("sub_item") or ""
            attribute = "/".join(filter(None, [item, sub_item]))
            rows.append(
                {
                    "group": group,
                    "title": result.get("title"),
                    "parent": result.get("parent"),
                    "parent_id": result.get("parent_id"),
                    "parent_article_type": result.get("parent_article_type"),
                    "item": item,
                    "sub_item": sub_item,
                    "attribute": attribute,
                    "validation_type": result.get("validation_type"),
                    "response": result.get("response"),
                    "expected_value": result.get("expected_value"),
                    "got_value": result.get("got_value"),
                    "advice": result.get("advice"),
                }
            )
    return rows, exceptions


def write_exceptions_json(exceptions: list, output_path: str) -> str:
    with open(output_path, "w", encoding="utf-8") as fp:
        if exceptions:
            fp.write(
                "\n".join(json.dumps(error, ensure_ascii=False) for error in exceptions)
            )
            fp.write("\n")
    return output_path


def write_csv(rows: list, output_csv: str) -> str:
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return output_csv

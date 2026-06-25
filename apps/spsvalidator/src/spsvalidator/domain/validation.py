from __future__ import annotations

import os
import zipfile
from pathlib import PurePosixPath

from spsvalidator.domain.metadata import extract_article_snapshot


def _extract_journal_data(xmltree):
    from packtools.sps.models.article_license import ArticleLicense
    from packtools.sps.pid_provider.models.journal_meta import (
        JournalID,
        Publisher,
        Title,
    )

    try:
        license_code = None
        for license_item in ArticleLicense(xmltree).licenses:
            code = license_item.get("code")
            if code:
                license_code = code
                break
        return {
            "abbrev_journal_title": Title(xmltree).abbreviated_journal_title,
            "publisher_name_list": Publisher(xmltree).publishers_names,
            "nlm_journal_title": JournalID(xmltree).nlm_ta,
            "license_code": license_code,
        }
    except Exception:
        return {}


def _iter_zip_xml_metadata(zip_path: str):
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            suffix = PurePosixPath(member.filename).suffix.lower()
            if suffix != ".xml":
                continue
            yield extract_article_snapshot(archive.read(member), member.filename)


def validate_sps_zip(zip_path: str) -> dict:
    from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre
    from packtools.sps.validation.xml_validator import get_validation_results

    if not os.path.isfile(zip_path):
        raise FileNotFoundError(zip_path)
    rows = []
    exceptions = []
    issues_by_parent = {}
    for xml_with_pre in XMLWithPre.create(path=zip_path):
        xmltree = xml_with_pre.xmltree
        rules = {"journal_data": _extract_journal_data(xmltree)}
        for result in get_validation_results(xmltree, rules):
            if not result:
                continue
            if result.get("response") == "exception":
                exceptions.append(result)
                continue
            if result.get("response") == "OK":
                continue
            group = result.get("group", "")
            item = result.get("item") or ""
            sub_item = result.get("sub_item") or ""
            attribute = "/".join(filter(None, [item, sub_item]))
            row = {
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
            rows.append(row)
            parent_key = row.get("parent") or row.get("parent_id") or ""
            if parent_key:
                issues_by_parent[parent_key] = issues_by_parent.get(parent_key, 0) + 1
    articles = list(_iter_zip_xml_metadata(zip_path))
    for article in articles:
        path_key = article.get("xml_path", "")
        article["issue_count"] = issues_by_parent.get(path_key, 0)
        article["article_status"] = "issue" if article["issue_count"] else "ok"
    return {"rows": rows, "exceptions": exceptions, "articles": articles}

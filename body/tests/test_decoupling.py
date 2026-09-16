import ast
from pathlib import Path

FORBIDDEN_ROOTS = {"front", "reference", "xml_manager"}


def test_body_app_does_not_import_sibling_apps():
    root = Path(__file__).resolve().parents[1]
    for path in root.rglob("*.py"):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in FORBIDDEN_ROOTS
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in FORBIDDEN_ROOTS

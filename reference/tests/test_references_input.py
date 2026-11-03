import json

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from rest_framework.test import APIClient

from reference.data_utils import (
    get_reference,
    resolve_reference_result,
    resolve_references_result,
)
from reference.marking import mark_references
from reference.models import ElementCitation, Reference, ReferenceStatus
from reference.utils.references import parse_reference_list


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, []),
        ("", []),
        ([], []),
        (["", "  ", "Ref A"], ["Ref A"]),
        ("Ref A\n\nRef B", ["Ref A", "Ref B"]),
        (["Ref A", "Ref B"], ["Ref A", "Ref B"]),
        (("Ref A", "Ref B"), ["Ref A", "Ref B"]),
        (123, ["123"]),
    ],
)
def test_parse_reference_list(value, expected):
    assert parse_reference_list(value) == expected


def test_mark_references_accepts_list(monkeypatch):
    class BatchStub:
        def __init__(self, messages, response_format, **_kwargs):
            self.response_format = response_format

        def run(self, text):
            schema = (
                self.response_format.get("schema", {}) if self.response_format else {}
            )
            if isinstance(schema.get("properties"), dict) and "results" in schema.get(
                "properties", {}
            ):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "results": [
                                            {"reftype": "journal", "title": "Ref A"},
                                            {"reftype": "journal", "title": "Ref B"},
                                        ]
                                    }
                                )
                            }
                        }
                    ]
                }
            return {
                "choices": [
                    {"message": {"content": '{"reftype":"journal"}'}},
                ]
            }

    monkeypatch.setattr(
        "reference.marking.get_provider", lambda *a, **k: BatchStub(*a, **k)
    )

    result = list(mark_references(["Ref A", "Ref B"]))

    assert len(result) == 2
    assert result[0]["references"] == "Ref A"
    assert result[1]["references"] == "Ref B"
    assert json.loads(result[0]["choices"][0])["title"] == "Ref A"
    assert json.loads(result[1]["choices"][0])["title"] == "Ref B"


def test_mark_references_string_and_list_are_equivalent(monkeypatch):
    class MarkStub:
        def __init__(self, messages, response_format, **_kwargs):
            self.response_format = response_format

        def run(self, text):
            schema = (
                self.response_format.get("schema", {}) if self.response_format else {}
            )
            if isinstance(schema.get("properties"), dict) and "results" in schema.get(
                "properties", {}
            ):
                lines = [
                    line.split(". ", 1)[1]
                    for line in text.splitlines()
                    if line[:1].isdigit() and ". " in line
                ]
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "results": [
                                            {"reftype": "journal", "title": line}
                                            for line in lines
                                        ]
                                    }
                                )
                            }
                        }
                    ]
                }
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"reftype": "journal", "title": text})
                        }
                    },
                ]
            }

    monkeypatch.setattr(
        "reference.marking.get_provider", lambda *a, **k: MarkStub(*a, **k)
    )

    from_list = list(mark_references(["Ref A", "Ref B"]))
    from_string = list(mark_references("Ref A\nRef B"))

    assert [item["references"] for item in from_list] == [
        item["references"] for item in from_string
    ]
    assert from_list[0]["choices"] == from_string[0]["choices"]


@pytest.mark.django_db
def test_resolve_reference_result_enriches_cached_doi(monkeypatch):
    citation = (
        "Alvares C. A. (2013a). Modeling monthly mean air temperature for Brazil. "
        "Theoretical and Applied Climatology, 113, 407–427. "
        "https://doi.org/10.1007/s00704-012-0796-6"
    )
    reference = Reference.objects.create(
        mixed_citation=citation,
        status=ReferenceStatus.READY,
    )
    ElementCitation.objects.create(
        reference=reference,
        marked={"reftype": "journal", "title": "Modeling", "source": "TAC"},
        marked_xml="<element-citation publication-type='journal'/>",
    )

    result = resolve_reference_result(citation, output_type="json")

    assert result["data"]["doi"] == "10.1007/s00704-012-0796-6"
    stored = reference.element_citation.first()
    assert stored.marked["doi"] == "10.1007/s00704-012-0796-6"
    assert "10.1007/s00704-012-0796-6" in stored.marked_xml


@pytest.mark.django_db
def test_resolve_reference_result_rewrites_suffixed_year():
    citation = (
        "Alvares C. A. (2013a). Modeling monthly mean air temperature for Brazil. "
        "Theoretical and Applied Climatology."
    )
    reference = Reference.objects.create(
        mixed_citation=citation,
        status=ReferenceStatus.READY,
    )
    ElementCitation.objects.create(
        reference=reference,
        marked={
            "reftype": "journal",
            "date": "2013a",
            "title": "Modeling monthly mean air temperature for Brazil",
            "source": "Theoretical and Applied Climatology",
        },
        marked_xml=(
            "<element-citation publication-type='journal'>"
            "<year>2013a</year></element-citation>"
        ),
    )

    resolve_reference_result(citation, output_type="json")

    stored = reference.element_citation.first()
    assert "<year>2013</year>" in stored.marked_xml
    assert "<year>2013a</year>" not in stored.marked_xml


@pytest.mark.django_db
def test_resolve_reference_result_enriches_cached_num():
    citation = (
        "Alvares, C. A. (2013b). Köppen’s climate classification map for Brazil. "
        "Meteorologische Zeitschrift, 22(6), 711–728."
    )
    reference = Reference.objects.create(
        mixed_citation=citation,
        status=ReferenceStatus.READY,
    )
    ElementCitation.objects.create(
        reference=reference,
        marked={"reftype": "journal", "title": "Köppen", "source": "MZ"},
        marked_xml="<element-citation publication-type='journal'/>",
    )

    result = resolve_reference_result(citation, output_type="json")

    assert result["data"]["num"] == 6
    assert result["data"]["vol"] == 22
    stored = reference.element_citation.first()
    assert stored.marked["num"] == 6
    assert "<issue>6</issue>" in stored.marked_xml
    assert "<volume>22</volume>" in stored.marked_xml


@pytest.mark.django_db
def test_resolve_reference_result_reuses_existing_reference():
    reference = Reference.objects.create(
        mixed_citation="Smith J. Nature. 2024.",
        status=ReferenceStatus.READY,
    )
    ElementCitation.objects.create(
        reference=reference,
        marked={"reftype": "journal", "title": "Cached"},
        marked_xml="<element-citation/>",
    )

    result = resolve_reference_result("Smith J. Nature. 2024.", output_type="json")

    assert result["mixed_citation"] == "Smith J. Nature. 2024."
    assert result["data"] == {"reftype": "journal", "title": "Cached"}
    assert (
        Reference.objects.filter(mixed_citation="Smith J. Nature. 2024.").count() == 1
    )


@pytest.mark.django_db
def test_resolve_reference_result_creates_and_marks_new_reference(monkeypatch):
    monkeypatch.setattr(
        "reference.data_utils.mark_reference",
        lambda _text: iter([json.dumps({"reftype": "journal", "title": "Created"})]),
    )

    User = get_user_model()
    user = User.objects.create_user(username="creator", password="pass")

    result = resolve_reference_result(
        "Jones A. Science. 2023.",
        user=user,
        output_type="json",
    )

    assert result["data"] == {"reftype": "journal", "title": "Created"}
    stored = Reference.objects.get(mixed_citation="Jones A. Science. 2023.")
    assert stored.creator == user
    assert stored.status == ReferenceStatus.READY
    assert stored.element_citation.count() == 1


@pytest.mark.django_db
def test_resolve_reference_result_handles_checksum_race(monkeypatch):
    citation = "Tuffi Santos LD. Planta Daninha 2007; 25(1):133-37."
    monkeypatch.setattr(
        "reference.data_utils.mark_reference",
        lambda _text: iter(
            [json.dumps({"reftype": "journal", "title": "Crescimento do eucalipto"})]
        ),
    )

    def racing_get_or_create(*args, **kwargs):
        Reference.objects.create(
            mixed_citation=citation,
            status=ReferenceStatus.READY,
        )
        raise IntegrityError("duplicate key value violates unique constraint")

    monkeypatch.setattr(
        Reference.objects,
        "get_or_create",
        racing_get_or_create,
    )

    result = resolve_reference_result(citation, output_type="json")

    assert result is not None
    assert result["mixed_citation"] == citation
    assert Reference.objects.filter(mixed_citation=citation).count() == 1
    assert (
        ElementCitation.objects.filter(reference__mixed_citation=citation).count() == 1
    )


@pytest.mark.django_db
def test_resolve_reference_result_ignores_figure_without_db(monkeypatch):
    monkeypatch.setattr(
        "reference.data_utils.mark_reference",
        lambda _text: iter([json.dumps({"is_reference": False})]),
    )

    before_refs = Reference.objects.count()
    before_cites = ElementCitation.objects.count()

    result = resolve_reference_result("Figure 1. Map of the study area.")

    assert result is None
    assert Reference.objects.count() == before_refs
    assert ElementCitation.objects.count() == before_cites


@pytest.mark.django_db
def test_resolve_reference_result_ignores_orcid_without_db(monkeypatch):
    monkeypatch.setattr(
        "reference.data_utils.mark_reference",
        lambda _text: iter([json.dumps({"is_reference": False})]),
    )

    before_refs = Reference.objects.count()
    before_cites = ElementCitation.objects.count()

    result = resolve_reference_result("https://orcid.org/0000-0003-4872-7252")

    assert result is None
    assert Reference.objects.count() == before_refs
    assert ElementCitation.objects.count() == before_cites


@pytest.mark.django_db
def test_resolve_reference_result_raises_without_db_when_llama_unavailable(
    monkeypatch,
):
    from reference.exceptions import ReferenceLlamaUnavailableError

    def raise_unavailable(_text):
        raise ReferenceLlamaUnavailableError(
            "Reference Llama service unavailable: 404 Client Error"
        )
        yield  # pragma: no cover

    monkeypatch.setattr("reference.data_utils.mark_reference", raise_unavailable)

    before_refs = Reference.objects.count()
    before_cites = ElementCitation.objects.count()

    with pytest.raises(ReferenceLlamaUnavailableError, match="404"):
        resolve_reference_result("Smith J. Nature. 2024.")

    assert Reference.objects.count() == before_refs
    assert ElementCitation.objects.count() == before_cites


@pytest.mark.django_db
def test_get_reference_deletes_when_llama_unavailable(monkeypatch):
    from reference.exceptions import ReferenceLlamaUnavailableError

    def raise_unavailable(_block):
        raise ReferenceLlamaUnavailableError(
            "Reference Llama service unavailable: 404 Client Error"
        )
        yield  # pragma: no cover

    monkeypatch.setattr("reference.data_utils.mark_references", raise_unavailable)

    reference = Reference.objects.create(
        mixed_citation="Smith J. Nature. 2024.",
        status=ReferenceStatus.CREATING,
    )
    ref_id = reference.id

    with pytest.raises(ReferenceLlamaUnavailableError, match="404"):
        get_reference(ref_id)

    assert not Reference.objects.filter(id=ref_id).exists()
    assert ElementCitation.objects.filter(reference_id=ref_id).count() == 0


@pytest.mark.django_db
def test_resolve_references_result_omits_non_references(monkeypatch):
    def fake_mark_reference_texts(texts):
        out = []
        for text in texts:
            if text.startswith("Figure"):
                out.append(json.dumps({"is_reference": False}))
            else:
                out.append(json.dumps({"reftype": "journal", "title": text}))
        return out

    monkeypatch.setattr(
        "reference.data_utils.mark_reference_texts",
        fake_mark_reference_texts,
    )

    results = resolve_references_result(
        [
            "Smith J. Nature. 2024.",
            "Figure 1. Map of the study area.",
            "Doe A. Science. 2023.",
        ]
    )

    assert [item["mixed_citation"] for item in results] == [
        "Smith J. Nature. 2024.",
        "Doe A. Science. 2023.",
    ]
    assert (
        Reference.objects.filter(
            mixed_citation="Figure 1. Map of the study area."
        ).count()
        == 0
    )
    assert Reference.objects.count() == 2


@pytest.mark.django_db
def test_get_reference_deletes_when_only_non_reference(monkeypatch):
    monkeypatch.setattr(
        "reference.data_utils.mark_references",
        lambda _block: iter(
            [
                {
                    "references": "Figure 1. Caption.",
                    "choices": [json.dumps({"is_reference": False})],
                }
            ]
        ),
    )
    reference = Reference.objects.create(
        mixed_citation="Figure 1. Caption.",
        status=ReferenceStatus.CREATING,
    )
    ref_id = reference.id

    get_reference(ref_id)

    assert not Reference.objects.filter(id=ref_id).exists()
    assert ElementCitation.objects.count() == 0


@pytest.mark.django_db
def test_get_reference_skips_non_reference_among_valid(monkeypatch):
    def fake_mark_references(reference_block):
        for ref_row in parse_reference_list(reference_block):
            if ref_row.startswith("Figure"):
                yield {
                    "references": ref_row,
                    "choices": [json.dumps({"is_reference": False})],
                }
            else:
                yield {
                    "references": ref_row,
                    "choices": [json.dumps({"reftype": "journal", "title": ref_row})],
                }

    monkeypatch.setattr(
        "reference.data_utils.mark_references",
        fake_mark_references,
    )
    reference = Reference.objects.create(
        mixed_citation="Ref A\nFigure 1. Caption.\nRef B",
        status=ReferenceStatus.CREATING,
    )

    get_reference(reference.id)

    reference.refresh_from_db()
    assert reference.status == ReferenceStatus.READY
    titles = list(reference.element_citation.values_list("marked", flat=True))
    assert [item["title"] for item in titles] == ["Ref A", "Ref B"]


@pytest.mark.django_db
def test_resolve_reference_result_returns_xml(monkeypatch):
    monkeypatch.setattr(
        "reference.data_utils.get_reference",
        lambda obj_id: None,
    )

    reference = Reference.objects.create(
        mixed_citation="XML Ref",
        status=ReferenceStatus.READY,
    )
    ElementCitation.objects.create(
        reference=reference,
        marked={"reftype": "journal"},
        marked_xml="<element-citation publication-type='journal'/>",
    )

    result = resolve_reference_result("XML Ref", output_type="xml")

    assert result["data"] == "<element-citation publication-type='journal'/>"


@pytest.mark.django_db
def test_resolve_references_result_processes_each_item(monkeypatch):
    monkeypatch.setattr(
        "reference.data_utils.get_reference",
        lambda obj_id: None,
    )

    for citation, title in (("Ref A", "A"), ("Ref B", "B")):
        reference = Reference.objects.create(
            mixed_citation=citation,
            status=ReferenceStatus.READY,
        )
        ElementCitation.objects.create(
            reference=reference,
            marked={"reftype": "journal", "title": title},
        )

    results = resolve_references_result(["Ref A", "Ref B"])

    assert len(results) == 2
    assert results[0]["data"]["title"] == "A"
    assert results[1]["data"]["title"] == "B"


@pytest.mark.django_db
def test_resolve_references_result_batches_uncached(monkeypatch):
    calls = []

    def fake_mark_reference_texts(texts):
        calls.append(list(texts))
        return [json.dumps({"reftype": "journal", "title": text}) for text in texts]

    monkeypatch.setattr(
        "reference.data_utils.mark_reference_texts",
        fake_mark_reference_texts,
    )

    results = resolve_references_result(["Ref A", "Ref B", "Ref C"])

    assert calls == [["Ref A", "Ref B", "Ref C"]]
    assert [item["data"]["title"] for item in results] == ["Ref A", "Ref B", "Ref C"]
    assert Reference.objects.count() == 3


@pytest.mark.django_db
def test_resolve_references_result_empty_list():
    assert resolve_references_result([]) == []


@pytest.mark.django_db
def test_get_reference_marks_multiline_mixed_citation(monkeypatch):
    marked_calls = []

    def fake_mark_references(reference_block):
        marked_calls.append(reference_block)
        for ref_row in parse_reference_list(reference_block):
            yield {
                "references": ref_row,
                "choices": [json.dumps({"reftype": "journal", "title": ref_row})],
            }

    monkeypatch.setattr("reference.data_utils.mark_references", fake_mark_references)

    reference = Reference.objects.create(
        mixed_citation="Ref A\nRef B",
        status=ReferenceStatus.CREATING,
    )

    get_reference(reference.id)

    reference.refresh_from_db()
    assert marked_calls == ["Ref A\nRef B"]
    assert reference.status == ReferenceStatus.READY
    assert reference.element_citation.count() == 2
    assert reference.element_citation.first().marked["title"] == "Ref A"


@pytest.mark.django_db
def test_api_accepts_reference_list(monkeypatch):
    monkeypatch.setattr(
        "reference.api.v1.views.resolve_references_result",
        lambda references, user=None, output_type="json": [
            {
                "mixed_citation": citation,
                "data": {"reftype": "journal", "title": citation},
            }
            for citation in parse_reference_list(references)
        ],
    )

    User = get_user_model()
    user = User.objects.create_user(username="apiuser", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/reference/",
        data=json.dumps(
            {
                "references": ["Ref A", "Ref B"],
                "type": "json",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["references"]) == 2
    assert payload["references"][0]["mixed_citation"] == "Ref A"
    assert payload["references"][1]["data"]["title"] == "Ref B"


@pytest.mark.django_db
def test_api_returns_503_when_llama_unavailable(monkeypatch):
    from reference.exceptions import ReferenceLlamaUnavailableError

    def raise_unavailable(*_args, **_kwargs):
        raise ReferenceLlamaUnavailableError(
            "Reference Llama service unavailable: 404 Client Error"
        )

    monkeypatch.setattr(
        "reference.api.v1.views.resolve_references_result",
        raise_unavailable,
    )

    User = get_user_model()
    user = User.objects.create_user(username="apiuser_llama_down", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    before_refs = Reference.objects.count()

    response = client.post(
        "/api/v1/reference/",
        data=json.dumps({"references": "Smith J. Nature. 2024.", "type": "json"}),
        content_type="application/json",
    )

    assert response.status_code == 503
    assert "Llama model is not available" in response.json()["error"]
    assert Reference.objects.count() == before_refs


@pytest.mark.django_db
def test_api_accepts_form_urlencoded(monkeypatch):
    monkeypatch.setattr(
        "reference.api.v1.views.resolve_references_result",
        lambda references, user=None, output_type="json": [
            {
                "mixed_citation": citation,
                "data": {"reftype": "journal", "title": citation},
            }
            for citation in parse_reference_list(references)
        ],
    )

    User = get_user_model()
    user = User.objects.create_user(username="apiuser_form", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/reference/",
        data={"references": "Ref A\nRef B", "type": "json"},
        format="multipart",
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["references"]) == 2
    assert payload["references"][0]["mixed_citation"] == "Ref A"


@pytest.mark.django_db
def test_api_keeps_single_string_response(monkeypatch):
    monkeypatch.setattr(
        "reference.api.v1.views.resolve_references_result",
        lambda references, user=None, output_type="json": [
            {
                "mixed_citation": "Ref A",
                "data": {"reftype": "journal"},
            }
        ],
    )

    User = get_user_model()
    user = User.objects.create_user(username="apiuser2", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/reference/",
        data=json.dumps(
            {
                "references": "Ref A",
                "type": "json",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["message"] == "reference: {'reftype': 'journal'}"


@pytest.mark.django_db
def test_api_multiline_string_returns_reference_list(monkeypatch):
    monkeypatch.setattr(
        "reference.api.v1.views.resolve_references_result",
        lambda references, user=None, output_type="json": [
            {"mixed_citation": citation, "data": {"reftype": "journal"}}
            for citation in parse_reference_list(references)
        ],
    )

    User = get_user_model()
    user = User.objects.create_user(username="apiuser3", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/reference/",
        data=json.dumps(
            {
                "references": "Ref A\nRef B",
                "type": "json",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert "references" in payload
    assert len(payload["references"]) == 2


@pytest.mark.django_db
def test_api_list_with_xml_type(monkeypatch):
    monkeypatch.setattr(
        "reference.api.v1.views.resolve_references_result",
        lambda references, user=None, output_type="json": [
            {
                "mixed_citation": citation,
                "data": f"<element-citation>{citation}</element-citation>",
            }
            for citation in parse_reference_list(references)
        ],
    )

    User = get_user_model()
    user = User.objects.create_user(username="apiuser4", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/reference/",
        data=json.dumps(
            {
                "references": ["Ref A", "Ref B"],
                "type": "xml",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["references"][0]["data"].startswith("<element-citation>")


@pytest.mark.django_db
def test_api_jats_returns_ref_list(monkeypatch):
    monkeypatch.setattr(
        "reference.api.v1.views.resolve_references_result",
        lambda references, user=None, output_type="json": [
            {
                "mixed_citation": citation,
                "data": (
                    f'<element-citation publication-type="journal">'
                    f"<article-title>{citation}</article-title>"
                    f"</element-citation>"
                ),
            }
            for citation in parse_reference_list(references)
        ],
    )

    User = get_user_model()
    user = User.objects.create_user(username="apiuser_jats", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/reference/",
        data=json.dumps(
            {
                "references": ["Ref A", "Ref B"],
                "type": "jats",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert "ref_list" in payload
    assert "<ref-list>" in payload["ref_list"]
    assert 'id="B1"' in payload["ref_list"]
    assert 'id="B2"' in payload["ref_list"]
    assert "<mixed-citation>Ref A</mixed-citation>" in payload["ref_list"]
    assert "<mixed-citation>Ref B</mixed-citation>" in payload["ref_list"]
    assert "element-citation" in payload["ref_list"]


@pytest.mark.django_db
def test_api_rejects_invalid_type(monkeypatch):
    User = get_user_model()
    user = User.objects.create_user(username="apiuser_badtype", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/reference/",
        data=json.dumps({"references": ["Ref A"], "type": "html"}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "type" in response.json()


@pytest.mark.django_db
def test_api_rejects_empty_references():
    User = get_user_model()
    user = User.objects.create_user(username="apiuser5", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/reference/",
        data=json.dumps({"references": [], "type": "json"}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"] == "No references provided"


@pytest.mark.django_db
def test_api_rejects_invalid_json():
    User = get_user_model()
    user = User.objects.create_user(username="apiuser6", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/reference/",
        data="{invalid",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "detail" in response.json()


@pytest.mark.django_db
def test_api_requires_authentication():
    client = APIClient()

    response = client.post(
        "/api/v1/reference/",
        data=json.dumps({"references": ["Ref A"], "type": "json"}),
        content_type="application/json",
    )

    assert response.status_code == 401

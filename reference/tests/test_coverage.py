import json
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponseRedirect
from lxml import etree
from rest_framework.test import APIClient

from reference.api.v1.serializers import (
    ReferenceDocxRequestSerializer,
    ReferencesInputField,
)
from reference.api.v1.views import ReferenceViewSet
from reference.create_forms import ReferenceCreateAdminForm
from reference.data_utils import (
    append_access_date,
    append_citation_pages,
    append_fpage_lpage,
    build_ref_list,
    get_number_of_month,
    get_reference,
    get_xml,
    parse_marked_choice,
    resolve_reference_result,
    resolve_references_result,
)
from reference.marking import mark_reference
from reference.models import Reference, ReferenceStatus
from reference.providers import get_provider
from reference.providers.http import Provider
from reference.tests.test_docx_api import make_docx_bytes
from reference.utils.references import extract_text_from_docx
from reference.wagtail_hooks import ReferenceCreateView


@pytest.mark.parametrize(
    "texto,expected",
    [
        ("cited may 2025", "05"),
        ("cited 2025", None),
    ],
)
def test_get_number_of_month(texto, expected):
    assert get_number_of_month(texto) == expected


def test_append_citation_pages_empty():
    root = etree.Element("element-citation")
    append_citation_pages(root, "   ")
    assert list(root) == []


def test_append_citation_pages_single_page_omits_lpage():
    root = etree.Element("element-citation")
    append_citation_pages(root, "244")
    assert root.find("fpage").text == "244"
    assert root.find("lpage") is None


def test_append_fpage_lpage_single_fpage_omits_lpage():
    root = etree.Element("element-citation")
    assert append_fpage_lpage(root, {"fpage": "237"}) is True
    assert root.find("fpage").text == "237"
    assert root.find("lpage") is None


def test_append_access_date_with_and_without_year():
    with_year = etree.Element("element-citation")
    append_access_date(with_year, "cited 2025")
    node = with_year.find("date-in-citation")
    assert node.get("iso-8601-date") == "2025-01-00"

    without_year = etree.Element("element-citation")
    append_access_date(without_year, "cited yesterday")
    node = without_year.find("date-in-citation")
    assert node.get("iso-8601-date") is None
    assert node.text == "cited yesterday"


def test_get_xml_malformed_json_returns_error():
    assert get_xml("{not-json").tag == "error"


def test_parse_marked_choice_dict_passthrough():
    marked = {"reftype": "journal", "title": "T"}
    assert parse_marked_choice(marked) is marked


def test_parse_marked_choice_empty_or_non_string():
    assert parse_marked_choice("") == {"raw": ""}
    assert parse_marked_choice(None) == {"raw": None}


def test_parse_marked_choice_extracts_json_after_think():
    marked = parse_marked_choice(
        '<think>slow reasoning</think>\n{"reftype":"journal","title":"T"}'
    )
    assert marked == {"reftype": "journal", "title": "T"}


def test_get_xml_authors_collab_variants():
    xml_node = get_xml(
        json.dumps(
            {
                "reftype": "journal",
                "authors": [
                    {"collab": "WHO"},
                    {"surname": "Smith", "fname": "J", "collab": "Team X"},
                ],
                "title": "T",
                "source": "S",
                "vol": 10,
                "num": 2,
            }
        )
    )
    person_group = xml_node.find("person-group")
    assert person_group.find("collab").text == "WHO"
    name = person_group.find("name")
    assert name.find("surname").text == "Smith"
    assert name.find("collab").text == "Team X"
    assert xml_node.find("volume").text == "10"
    assert xml_node.find("issue").text == "2"


def test_get_xml_book_publisher_vol_doi():
    xml_node = get_xml(
        json.dumps(
            {
                "reftype": "book",
                "source": "Soil biology",
                "vol": 2,
                "publisher": "CAB",
                "doi": "10.1000/book",
                "date": 1993,
            }
        )
    )
    assert xml_node.find("volume").text == "2"
    assert xml_node.find("publisher-name").text == "CAB"
    assert xml_node.find("pub-id").text == "10.1000/book"


def test_get_xml_thesis():
    xml_node = get_xml(
        json.dumps(
            {
                "reftype": "thesis",
                "title": "PhD thesis title",
                "degree": "PhD",
                "organization": "USP",
                "date": 2020,
            }
        )
    )
    assert xml_node.get("publication-type") == "thesis"
    assert xml_node.find("source").text == "PhD thesis title"
    assert xml_node.find("comment").text == "PhD"
    assert xml_node.find("publisher-name").text == "USP"


def test_get_xml_confproc_location_num_and_org_location():
    xml_node = get_xml(
        json.dumps(
            {
                "reftype": "confproc",
                "title": "Proceedings of the 17th Workshop for Bishops",
                "source": "Addiction and compulsive behaviors",
                "location": "Dallas, TX",
                "num": 17,
                "organization": "National Catholic Bioethics Center (US)",
                "org_location": "Boston",
                "num_pages": 258,
                "date": 2000,
            }
        )
    )
    assert xml_node.find("conf-loc").text == "Dallas, TX"
    assert xml_node.find("conf-num").text == "17"
    assert xml_node.find("publisher-loc").text == "Boston"
    assert xml_node.find("size").text == "258"


def test_get_xml_data_access_id():
    xml_node = get_xml(
        json.dumps(
            {
                "reftype": "data",
                "title": "Dataset",
                "source": "SciELO Data",
                "doi": "https://doi.org/10.48331/scielodata.5Z4TMP",
                "access_id": "UNF:6:Neyjad4du3rFprhupCXizA== [fileUNF]",
                "date": 2024,
            }
        )
    )
    assert xml_node.find("pub-id").text == "10.48331/scielodata.5Z4TMP"
    assert xml_node.find("comment").text.startswith("UNF:6:")


def test_get_xml_confproc():
    xml_node = get_xml(
        json.dumps(
            {
                "reftype": "confproc",
                "conf_name": "IGARSS",
                "source": "Proceedings",
                "conf_loc": "Toulouse",
                "conf_date": 2003,
                "conf_num": 23,
                "organization": "IEEE",
                "doi": "10.1000/conf",
            }
        )
    )
    assert xml_node.find("conf-name").text == "IGARSS"
    assert xml_node.find("source").text == "Proceedings"
    assert xml_node.find("conf-loc").text == "Toulouse"
    assert xml_node.find("conf-date").text == "2003"
    assert xml_node.find("conf-num").text == "23"
    assert xml_node.find("publisher-name").text == "IEEE"
    assert xml_node.find("pub-id").text == "10.1000/conf"

    titled = get_xml(json.dumps({"reftype": "confproc", "title": "Named Conference"}))
    assert titled.find("conf-name").text == "Named Conference"


def test_get_xml_data_extra_fields():
    xml_node = get_xml(
        json.dumps(
            {
                "reftype": "data",
                "title": "Dataset",
                "source": "SciELO Data",
                "version": "1.0",
                "uri": "https://example.org/data",
                "organization": "SciELO",
                "access_date": "cited 12 March 2025",
                "date": 2025,
            }
        )
    )
    assert xml_node.find("version").text == "1.0"
    assert xml_node.find("ext-link").text == "https://example.org/data"
    assert xml_node.find("publisher-name").text == "SciELO"
    assert xml_node.find("date-in-citation").get("iso-8601-date") == "2025-03-00"


def test_get_xml_webpage_software_legal_and_other():
    webpage = get_xml(
        json.dumps(
            {
                "reftype": "webpage",
                "source": "Home tips",
                "country": "US",
                "doi": "10.1000/web",
                "access_date": "cited Jan 2024",
            }
        )
    )
    assert webpage.find("source").text == "Home tips"
    assert webpage.find("publisher-loc").text == "US"
    assert webpage.find("pub-id").text == "10.1000/web"

    software = get_xml(
        json.dumps(
            {
                "reftype": "software",
                "title": "R",
                "version": "4.3",
                "uri": "https://www.R-project.org/",
            }
        )
    )
    assert software.find("version").text == "4.3"

    legal = get_xml(
        json.dumps(
            {
                "reftype": "legal-doc",
                "title": "Lei 1/2020",
                "organization": "Brasil",
            }
        )
    )
    assert legal.find("source").text == "Lei 1/2020"

    other = get_xml(
        json.dumps(
            {
                "reftype": "other",
                "source": "Misc source",
                "doi": "10.1000/other",
                "uri": "https://example.org/other",
            }
        )
    )
    assert other.find("source").text == "Misc source"
    assert other.find("pub-id").text == "10.1000/other"
    assert other.find("ext-link").text == "https://example.org/other"

    other_title = get_xml(json.dumps({"reftype": "other", "title": "Other title"}))
    assert other_title.find("source").text == "Other title"


def test_build_ref_list_skips_missing_and_invalid_xml():
    xml_text = build_ref_list(
        [
            {"mixed_citation": "Missing data"},
            {"mixed_citation": "Bad xml", "data": "<not-closed>"},
        ]
    )
    root = etree.fromstring(xml_text.encode("utf-8"))
    refs = root.findall("ref")
    assert refs[0].find("element-citation") is None
    assert refs[1].find("element-citation") is None


@pytest.mark.django_db
def test_get_reference_handles_invalid_json_choice(monkeypatch):
    monkeypatch.setattr(
        "reference.data_utils.mark_references",
        lambda _block: iter([{"references": "Ref A", "choices": ["{not-json"]}]),
    )
    reference = Reference.objects.create(
        mixed_citation="Ref A",
        status=ReferenceStatus.CREATING,
    )
    get_reference(reference.id)
    reference.refresh_from_db()
    assert reference.status == ReferenceStatus.READY
    marked = list(reference.element_citation.values_list("marked", flat=True))
    assert marked == [{"raw": "{not-json"}]


@pytest.mark.django_db
def test_get_reference_skips_choice_without_reftype(monkeypatch):
    monkeypatch.setattr(
        "reference.data_utils.mark_references",
        lambda _block: iter(
            [
                {
                    "references": "Ref A",
                    "choices": [
                        {"title": "No type"},
                        {"reftype": "journal", "title": "Ok"},
                    ],
                }
            ]
        ),
    )
    reference = Reference.objects.create(
        mixed_citation="Ref A",
        status=ReferenceStatus.CREATING,
    )
    get_reference(reference.id)
    reference.refresh_from_db()
    assert reference.status == ReferenceStatus.READY
    marked = list(reference.element_citation.values_list("marked", flat=True))
    assert marked == [{"reftype": "journal", "title": "Ok"}]


@pytest.mark.django_db
def test_resolve_reference_result_ignores_mark_without_reftype(monkeypatch):
    monkeypatch.setattr(
        "reference.data_utils.mark_reference",
        lambda _text: iter([{"title": "Missing type"}]),
    )
    before_refs = Reference.objects.count()
    result = resolve_reference_result("Incomplete mark citation.")
    assert result is None
    assert Reference.objects.count() == before_refs


@pytest.mark.django_db
def test_get_reference_reraises_missing_object():
    with pytest.raises(Reference.DoesNotExist):
        get_reference(999999)


def test_marking_reports_unexpected_error(monkeypatch):
    monkeypatch.setattr(
        "reference.marking.get_provider",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    result = list(mark_reference("Ref A"))
    assert len(result) == 1
    assert "unexpected error" in result[0].lower()
    assert "boom" in result[0]


def test_get_provider_returns_provider(settings):
    settings.REFERENCE_ENABLED = True
    settings.REFERENCE_URL = "http://llama.example:11434"
    provider = get_provider([], None)
    assert isinstance(provider, Provider)
    assert provider.url == "http://llama.example:11434"


@pytest.mark.django_db
def test_reference_str():
    reference = Reference.objects.create(mixed_citation="Smith J. Nature. 2024.")
    assert str(reference) == "Smith J. Nature. 2024."


def test_references_input_field_to_representation():
    field = ReferencesInputField()
    assert field.to_representation(["Ref A"]) == ["Ref A"]


def test_docx_serializer_rejects_empty_file():
    from rest_framework.exceptions import ValidationError

    upload = MagicMock()
    upload.name = "empty.docx"
    upload.size = 0
    serializer = ReferenceDocxRequestSerializer()
    with pytest.raises(ValidationError, match="Empty file"):
        serializer.validate_file(upload)


def test_api_reference_rejects_non_mapping_body():
    view = ReferenceViewSet()
    request = MagicMock()
    request.data = ["not", "a", "mapping"]
    response = view.api_reference(request)
    assert response.status_code == 400
    assert json.loads(response.content) == {"error": "Error processing"}


@pytest.mark.django_db
def test_api_docx_read_failure(monkeypatch):
    monkeypatch.setattr(
        "reference.utils.references.extract_text_from_docx",
        lambda *a, **k: (_ for _ in ()).throw(OSError("broken")),
    )
    User = get_user_model()
    user = User.objects.create_user(username="docxfail", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)
    upload = SimpleUploadedFile(
        "article.docx",
        b"PK fake",
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    response = client.post(
        "/api/v1/reference/docx/",
        data={"file": upload},
        format="multipart",
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Could not read DOCX file"


@pytest.mark.django_db
def test_reference_create_view_form_valid(monkeypatch):
    User = get_user_model()
    user = User.objects.create_user(username="wagtail-ref", password="pass")
    resolve_calls = []

    def fake_mark_texts(texts):
        return [
            json.dumps({"reftype": "journal", "title": text, "source": "Nature"})
            for text in texts
        ]

    monkeypatch.setattr("reference.data_utils.mark_reference_texts", fake_mark_texts)

    original_resolve = resolve_references_result

    def tracking_resolve(references, user=None, output_type="json"):
        resolve_calls.append(
            {"references": references, "user": user, "output_type": output_type}
        )
        return original_resolve(references, user=user, output_type=output_type)

    monkeypatch.setattr(
        "reference.wagtail_hooks.resolve_references_result",
        tracking_resolve,
    )

    view = ReferenceCreateView()
    view.request = MagicMock(user=user)
    view.get_success_url = lambda: "/admin/snippets/reference/reference/"

    citation_text = (
        "Smith J. Nature. 2024.\n\nDoe A. Science. 2023.\nSmith J. Nature. 2024."
    )
    form = MagicMock()
    form.cleaned_data = {"mixed_citation": citation_text}

    response = view.form_valid(form)

    assert isinstance(response, HttpResponseRedirect)
    assert len(resolve_calls) == 1
    assert resolve_calls[0]["references"] == citation_text
    assert resolve_calls[0]["user"] == user
    assert resolve_calls[0]["output_type"] == "json"
    assert Reference.objects.count() == 2
    assert all(ref.status == ReferenceStatus.READY for ref in Reference.objects.all())
    assert all(ref.element_citation.exists() for ref in Reference.objects.all())


@pytest.mark.django_db
def test_reference_create_view_shows_error_when_llama_unavailable(monkeypatch):
    from reference.exceptions import ReferenceLlamaUnavailableError

    User = get_user_model()
    user = User.objects.create_user(username="wagtail-llama-down", password="pass")
    error_messages = []

    def raise_unavailable(*_args, **_kwargs):
        raise ReferenceLlamaUnavailableError(
            "Reference Llama service unavailable: 404 Client Error"
        )

    monkeypatch.setattr(
        "reference.wagtail_hooks.resolve_references_result",
        raise_unavailable,
    )
    monkeypatch.setattr(
        "reference.wagtail_hooks.messages.error",
        lambda request, message: error_messages.append(str(message)),
    )

    view = ReferenceCreateView()
    view.request = MagicMock(user=user)
    view.render_to_response = MagicMock(return_value="rendered")
    view.get_context_data = MagicMock(return_value={"form": MagicMock()})

    form = MagicMock()
    form.cleaned_data = {"mixed_citation": "Smith J. Nature. 2024."}

    before_refs = Reference.objects.count()
    response = view.form_valid(form)

    assert response == "rendered"
    assert Reference.objects.count() == before_refs
    assert len(error_messages) == 1
    assert "Llama model is not available" in error_messages[0]
    assert "404" in error_messages[0]


@pytest.mark.django_db
def test_reference_create_view_keeps_panels_and_docx():
    view = ReferenceCreateView()
    view.model = Reference
    view.panel = view.get_panel()
    form_class = view.get_form_class()

    assert "mixed_citation" in form_class.base_fields
    assert "docx_file" in form_class.base_fields
    assert "element_citation" in form_class.formsets
    panel_fields = [
        getattr(child, "field_name", None) or getattr(child, "relation_name", None)
        for child in view.panel.children
    ]
    assert panel_fields == [
        "mixed_citation",
        "docx_file",
        "element_citation",
    ]


@pytest.mark.django_db
def test_reference_create_admin_form_rejects_non_docx():
    form = ReferenceCreateAdminForm(
        data={"mixed_citation": ""},
        files={
            "docx_file": SimpleUploadedFile(
                "article.txt",
                b"References\nRef A",
                content_type="text/plain",
            )
        },
    )
    assert not form.is_valid()
    assert "docx_file" in form.errors


def test_reference_create_admin_form_clean_docx_rejects_empty_file():
    from django.core.exceptions import ValidationError

    class EmptyUpload:
        name = "empty.docx"
        size = 0

    form = ReferenceCreateAdminForm()
    form.cleaned_data = {"docx_file": EmptyUpload()}
    with pytest.raises(ValidationError, match="Empty file"):
        form.clean_docx_file()


def test_extract_text_from_docx_respects_limit_chars(tmp_path):
    docx_path = tmp_path / "sample.docx"
    docx_path.write_bytes(
        make_docx_bytes(["References", "Smith J. Nature. 2024." * 20])
    )
    text = extract_text_from_docx(str(docx_path), limit_chars=40)
    assert len(text) == 40


@pytest.mark.django_db
def test_reference_create_admin_form_requires_text_or_docx():
    form = ReferenceCreateAdminForm(data={"mixed_citation": "   "})
    assert not form.is_valid()
    assert form.non_field_errors()


@pytest.mark.django_db
def test_reference_create_admin_form_rejects_docx_without_section():
    upload = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(["Introduction", "No refs here"]),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    form = ReferenceCreateAdminForm(
        data={"mixed_citation": ""},
        files={"docx_file": upload},
    )
    assert not form.is_valid()
    assert "No references section found in DOCX" in form.errors.as_text()


@pytest.mark.django_db
def test_reference_create_admin_form_docx_extracts_references():
    upload = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(
            [
                "Introduction",
                "References",
                "Smith J. Nature. 2024.",
                "Doe A. Science. 2023.",
            ]
        ),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    form = ReferenceCreateAdminForm(
        data={"mixed_citation": "ignored text"},
        files={"docx_file": upload},
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["mixed_citation"] == (
        "Smith J. Nature. 2024.\nDoe A. Science. 2023."
    )


@pytest.mark.django_db
def test_reference_create_view_form_valid_from_docx(monkeypatch):
    User = get_user_model()
    user = User.objects.create_user(username="wagtail-docx", password="pass")
    resolve_calls = []

    def fake_mark_texts(texts):
        return [
            json.dumps({"reftype": "journal", "title": text, "source": "Nature"})
            for text in texts
        ]

    monkeypatch.setattr("reference.data_utils.mark_reference_texts", fake_mark_texts)

    original_resolve = resolve_references_result

    def tracking_resolve(references, user=None, output_type="json"):
        resolve_calls.append(
            {"references": references, "user": user, "output_type": output_type}
        )
        return original_resolve(references, user=user, output_type=output_type)

    monkeypatch.setattr(
        "reference.wagtail_hooks.resolve_references_result",
        tracking_resolve,
    )

    upload = SimpleUploadedFile(
        "article.docx",
        make_docx_bytes(
            [
                "References",
                "Smith J. Nature. 2024.",
                "Doe A. Science. 2023.",
            ]
        ),
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )
    form = ReferenceCreateAdminForm(
        data={"mixed_citation": ""},
        files={"docx_file": upload},
    )
    assert form.is_valid(), form.errors

    view = ReferenceCreateView()
    view.request = MagicMock(user=user)
    view.get_success_url = lambda: "/admin/snippets/reference/reference/"

    response = view.form_valid(form)

    assert isinstance(response, HttpResponseRedirect)
    assert len(resolve_calls) == 1
    assert resolve_calls[0]["references"] == (
        "Smith J. Nature. 2024.\nDoe A. Science. 2023."
    )
    assert resolve_calls[0]["user"] == user
    assert Reference.objects.count() == 2
    assert all(ref.status == ReferenceStatus.READY for ref in Reference.objects.all())
    assert all(ref.element_citation.exists() for ref in Reference.objects.all())

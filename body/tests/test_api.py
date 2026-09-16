import json
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from body.exceptions import BodyLlamaUnavailableError
from body.models import Body

SAMPLE_MARKED = {
    "sections": [
        {
            "id": "sec1",
            "sec_type": "intro",
            "title": "INTRODUÇÃO",
            "content": [
                {
                    "type": "p",
                    "text": (
                        "O empreendedorismo social promove o bem-estar coletivo.1-3 "
                        "O modelo está na Figura 1."
                    ),
                    "xrefs": [
                        {"ref_type": "bibr", "rid": "B1", "text": "1-3"},
                        {"ref_type": "fig", "rid": "f1", "text": "Figura 1"},
                    ],
                }
            ],
            "sections": [],
        },
        {
            "id": "sec2",
            "sec_type": "methods",
            "title": "MÉTODO",
            "content": [{"type": "p", "text": "Estudo teórico-reflexivo."}],
            "sections": [],
        },
        {
            "id": "sec3",
            "sec_type": "results|discussion",
            "title": "RESULTADOS E DISCUSSÃO",
            "content": [
                {"type": "p", "text": "A reflexão deu origem a dois eixos."},
                {
                    "type": "fig",
                    "id": "f1",
                    "label": "Figura 1",
                    "caption": "Sistemas inter-relacionados da teoria.",
                    "attrib": "Elaboração própria.",
                },
            ],
            "sections": [],
        },
    ]
}


@pytest.mark.django_db
def test_api_marks_body_json(monkeypatch):
    monkeypatch.setattr(
        "body.data_utils.mark_body",
        lambda _text: json.dumps(SAMPLE_MARKED),
    )
    User = get_user_model()
    user = User.objects.create_user(username="bodyuser", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/body/",
        data=json.dumps(
            {
                "body": "INTRODUÇÃO\nO empreendedorismo social.\nMÉTODO\nEstudo.",
                "type": "json",
                "language": "pt",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["sections"][0]["title"] == "INTRODUÇÃO"
    assert payload["data"]["sections"][0]["sec_type"] == "intro"
    assert Body.objects.count() == 1


@pytest.mark.django_db
def test_api_marks_body_xml(monkeypatch):
    monkeypatch.setattr(
        "body.data_utils.mark_body",
        lambda _text: json.dumps(SAMPLE_MARKED),
    )
    User = get_user_model()
    user = User.objects.create_user(username="bodyxml", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/body/",
        data=json.dumps(
            {
                "body": "INTRODUÇÃO\nO empreendedorismo social.\nMÉTODO\nEstudo.",
                "type": "xml",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    xml = response.json()["data"]
    assert xml.strip().startswith("<body")
    assert 'sec-type="intro"' in xml
    assert "<title>INTRODUÇÃO</title>" in xml
    assert 'id="f1"' in xml
    assert 'ref-type="bibr"' in xml
    assert 'rid="B1"' in xml


@pytest.mark.django_db
def test_api_requires_body():
    User = get_user_model()
    user = User.objects.create_user(username="bodyempty", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/body/",
        data=json.dumps({"type": "json"}),
        content_type="application/json",
    )
    assert response.status_code == 400

    response = client.post(
        "/api/v1/body/",
        data=json.dumps({"body": "   ", "type": "json"}),
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_api_requires_auth():
    client = APIClient()
    response = client.post(
        "/api/v1/body/",
        data=json.dumps({"body": "INTRODUÇÃO\nTexto.", "type": "json"}),
        content_type="application/json",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_api_returns_503_without_persisting(monkeypatch):
    def raise_unavailable(_text):
        raise BodyLlamaUnavailableError("Body Llama service unavailable")

    monkeypatch.setattr("body.data_utils.mark_body", raise_unavailable)
    User = get_user_model()
    user = User.objects.create_user(username="bodydown", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/body/",
        data=json.dumps({"body": "INTRODUÇÃO\nTexto.", "type": "json"}),
        content_type="application/json",
    )
    assert response.status_code == 503
    assert "Llama model is not available" in response.json()["error"]
    assert Body.objects.count() == 0


@pytest.mark.django_db
def test_api_reuses_checksum_cache(monkeypatch):
    calls = MagicMock(return_value=json.dumps(SAMPLE_MARKED))
    monkeypatch.setattr("body.data_utils.mark_body", calls)
    User = get_user_model()
    user = User.objects.create_user(username="bodycache", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    payload = json.dumps(
        {"body": "INTRODUÇÃO\nO empreendedorismo social.", "type": "json"}
    )
    first = client.post("/api/v1/body/", data=payload, content_type="application/json")
    second = client.post("/api/v1/body/", data=payload, content_type="application/json")

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls.call_count == 1
    assert Body.objects.count() == 1

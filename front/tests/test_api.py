import json
from unittest.mock import MagicMock

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from front.exceptions import FrontLlamaUnavailableError
from front.models import Front

SAMPLE_MARKED = {
    "titles": [{"kind": "main", "text": "Título de teste"}],
    "authors": [
        {
            "given_names": "Ana",
            "surname": "Silva",
            "affiliations": ["aff1"],
        }
    ],
    "affiliations": [
        {
            "id": "aff1",
            "orgname": "Universidade Exemplo",
            "city": "São Paulo",
            "country": "Brasil",
            "country_code": "BR",
        }
    ],
    "abstracts": [{"kind": "main", "title": "Resumo", "text": "Texto do resumo."}],
    "keywords": [{"language": "pt", "keywords": ["ciência", "dados"]}],
    "article_ids": [{"pub_id_type": "doi", "value": "10.1590/example"}],
}


@pytest.mark.django_db
def test_api_marks_front_json(monkeypatch):
    monkeypatch.setattr(
        "front.data_utils.mark_front",
        lambda _text: json.dumps(SAMPLE_MARKED),
    )
    User = get_user_model()
    user = User.objects.create_user(username="frontuser", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/front/",
        data=json.dumps(
            {
                "front": "Título de teste\nAna Silva\nDOI: 10.1590/example",
                "type": "json",
                "language": "pt",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["titles"][0]["text"] == "Título de teste"
    assert payload["data"]["article_ids"][0]["value"] == "10.1590/example"
    assert Front.objects.count() == 1


@pytest.mark.django_db
def test_api_marks_front_xml(monkeypatch):
    monkeypatch.setattr(
        "front.data_utils.mark_front",
        lambda _text: json.dumps(SAMPLE_MARKED),
    )
    User = get_user_model()
    user = User.objects.create_user(username="frontxml", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/front/",
        data=json.dumps({"front": "Título de teste\nAna Silva", "type": "xml"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    xml = response.json()["data"]
    assert xml.strip().startswith("<front")
    assert "<article-meta>" in xml
    assert "<article-title>Título de teste</article-title>" in xml


@pytest.mark.django_db
def test_api_requires_front():
    User = get_user_model()
    user = User.objects.create_user(username="frontempty", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/front/",
        data=json.dumps({"type": "json"}),
        content_type="application/json",
    )
    assert response.status_code == 400

    response = client.post(
        "/api/v1/front/",
        data=json.dumps({"front": "   ", "type": "json"}),
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_api_requires_auth():
    client = APIClient()
    response = client.post(
        "/api/v1/front/",
        data=json.dumps({"front": "Título", "type": "json"}),
        content_type="application/json",
    )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_api_returns_503_without_persisting(monkeypatch):
    def raise_unavailable(_text):
        raise FrontLlamaUnavailableError("Front Llama service unavailable")

    monkeypatch.setattr("front.data_utils.mark_front", raise_unavailable)
    User = get_user_model()
    user = User.objects.create_user(username="frontdown", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v1/front/",
        data=json.dumps({"front": "Título de teste", "type": "json"}),
        content_type="application/json",
    )
    assert response.status_code == 503
    assert "Llama model is not available" in response.json()["error"]
    assert Front.objects.count() == 0


@pytest.mark.django_db
def test_api_reuses_checksum_cache(monkeypatch):
    calls = MagicMock(return_value=json.dumps(SAMPLE_MARKED))
    monkeypatch.setattr("front.data_utils.mark_front", calls)
    User = get_user_model()
    user = User.objects.create_user(username="frontcache", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)

    body = json.dumps({"front": "Título de teste\nAna Silva", "type": "json"})
    first = client.post("/api/v1/front/", data=body, content_type="application/json")
    second = client.post("/api/v1/front/", data=body, content_type="application/json")

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls.call_count == 1
    assert Front.objects.count() == 1

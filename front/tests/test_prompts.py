import json

from front.prompts import MESSAGES, RESPONSE_FORMAT


def test_prompt_instructs_particles_dates_city_and_no_default_subject():
    system = MESSAGES[0]["content"]
    assert "given_names" in system
    assert "never in surname" in system
    assert "do Carmo" in system
    assert "municipality" in system
    assert "orgdiv1" in system
    assert "subj_group_type" in system
    assert "subj-group-type" in system
    assert "always heading" in system
    assert "do not default to Article" in system
    assert "Do not copy names, ORCID, DOI" in system
    assert "Use only dates written in this input" in system
    assert "day/month/year" in system
    assert "22/12/2025" in system
    assert "month 12" in system
    assert "23 Sept. 2025" in system
    assert "23 de setembro de 2025" in system
    assert "Submitted" in system
    assert "Aprovado" in system
    assert "corresp true only for the corresponding author" in system
    assert "ORCID belongs to the name it appears next to" in system
    assert "Never write the strings null" in system
    assert "Articles/Artigos" in system
    assert "split only on semicolons" in system
    assert "Violence against Women" in system
    assert "Palabras clave" in system
    assert "do not add a language or term that is not written" in system
    assert "never SciELO SPS" in system
    assert "Omit history entirely" in system
    assert "FAPESP" in system and "CNPq" in system
    assert "print/impresso/printed -> ppub" in system
    assert "online/eletrônico/on-line -> epub" in system
    assert "never copy ISSN values from the example" in system
    assert "omit this key" in system
    assert "Never paste abstract text" in system
    assert "Keep the JSON compact" in system
    assert RESPONSE_FORMAT == {"type": "json_object"}


def test_few_shot_is_not_the_bn_2025_1870_fixture():
    user = MESSAGES[1]["content"]
    assistant = MESSAGES[2]["content"]
    leaked = "10.1590/1676-0611-BN-2025-1870"
    assert leaked not in user
    assert leaked not in assistant
    assert "Biota Neotropica" not in user
    assert "Jéssica" not in user
    assert "10 January 2025" not in user
    assert "22/12/2025" not in user
    assert "22/12/2025" not in assistant
    assert "Biota Neotropica" not in MESSAGES[0]["content"]


def test_few_shot_shows_particles_two_authors_city_and_funding():
    user = MESSAGES[1]["content"]
    marked = json.loads(MESSAGES[2]["content"])
    assert "Ana P. da Silva" in user
    assert "Carlos R. do Nascimento" in user
    assert "Itirapina" in user
    assert "Campus do Interior" in user
    assert "CNPq 312345/2023-0" in user
    assert "12(3): e20240099" in user
    assert "ISSN 1111-2222 (Print)" in user
    assert "ISSN 3333-4444 (Online)" in user
    assert marked["journal"]["issns"] == [
        {"pub_type": "ppub", "value": "1111-2222"},
        {"pub_type": "epub", "value": "3333-4444"},
    ]
    assert (
        "Keywords: Seasonal rainfall; Forest birds; Cerrado; "
        "Bioindicators; Conservation"
    ) in user
    assert marked["keywords"] == [
        {
            "language": "en",
            "title": "Keywords",
            "keywords": [
                "Seasonal rainfall",
                "Forest birds",
                "Cerrado",
                "Bioindicators",
                "Conservation",
            ],
        },
        {
            "language": "pt",
            "title": "Palavras-chave",
            "keywords": [
                "Chuva sazonal",
                "Aves florestais",
                "Cerrado",
                "Bioindicadores",
                "Conservação",
            ],
        },
    ]

    authors = marked["authors"]
    assert authors[0]["given_names"] == "Ana P. da"
    assert authors[0]["surname"] == "Silva"
    assert authors[0]["corresp"] is True
    assert authors[1]["given_names"] == "Carlos R. do"
    assert authors[1]["surname"] == "Nascimento"
    assert "corresp" not in authors[1]

    aff2 = marked["affiliations"][1]
    assert aff2["city"] == "Itirapina"
    assert aff2["orgdiv1"] == "Campus do Interior"

    assert "07/03/2024" in user
    received = marked["history"][0]
    assert received == {"type": "received", "day": "07", "month": "03", "year": "2024"}
    assert marked["history"][1] == {
        "type": "accepted",
        "day": "18",
        "month": "11",
        "year": "2024",
    }
    assert marked["funding"]["awards"][0]["funding_source"] == "CNPq"
    assert "Original Article" in user
    assert marked["categories"] == [
        {"subj_group_type": "heading", "subject": "Original Article"}
    ]

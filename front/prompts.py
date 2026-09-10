MESSAGES = [
    {
        "role": "system",
        "content": (
            "You extract SciELO SPS 1.10 <front> metadata from article front matter. "
            "Respond ONLY with one JSON object. Omit keys that are not in the text. "
            "Never invent DOI, ISSN, ORCID, dates, volume, issue, pages, funding, "
            "license, counts, or journal identifiers. "
            "JSON keys: journal, article_ids, categories, titles, authors, "
            "affiliations, author_notes, pub_dates, volume, issue, fpage, lpage, "
            "elocation_id, abstracts, keywords, history, permissions, counts, funding. "
            "journal: journal_ids [{type: publisher-id|nlm-ta, value}], "
            "journal_title, abbrev_journal_title, issns [{pub_type: epub|ppub, value}], "
            "publisher_name. "
            "article_ids: [{pub_id_type: doi|publisher-id|other, value}]; doi is the "
            "bare id without https://doi.org/. "
            "categories: [{subject}]. "
            "titles: [{kind: main|translated, text, language?}]; language only on "
            "translated. "
            "authors: [{contrib_type (default author), given_names, surname, collab, "
            "orcid (bare 0000-0000-0000-0000), affiliations [aff ids], corresp bool, "
            "roles []}]. "
            "affiliations: [{id, label, original, orgname, orgdiv1, orgdiv2, city, "
            "state, postal_code, country, country_code (ISO 3166-1 alpha-2), email}]. "
            "author_notes: {corresp, fns:[{text}]}. "
            "pub_dates: [{type: pub|collection, day, month, year, season}]. "
            "history: [{type: received|rev-recd|accepted, day, month, year}]. "
            "abstracts: [{kind: main|translated, title, text, language?, "
            "abstract_type?, sections:[{title, text}]}]; language only on translated; "
            "abstract_type only key-points when the text is key points. "
            "keywords: [{language, title, keywords:[]}]. "
            "permissions: {copyright_statement, copyright_year, copyright_holder, "
            "license_href, license_p}. "
            "counts: {fig_count, table_count, equation_count, ref_count} as strings "
            "only when stated. "
            "funding: {awards:[{funding_source, award_id}], funding_statement}."
        ),
    },
    {
        "role": "user",
        "content": (
            "Biota Neotropica\n"
            "ISSN 1676-0611\n"
            "What do scientific collections reveal about the past of the Amazon?\n"
            "O que as coleções científicas revelam sobre o passado da Amazônia?\n"
            "Jéssica S. de Lima https://orcid.org/0000-0002-3193-9315\n"
            "1 Instituto de Pesquisas Ambientais, São Paulo, SP, Brasil.\n"
            "* Correspondence: jessica@example.com\n"
            "Received: 10 January 2025. Accepted: 21 April 2026.\n"
            "DOI: 10.1590/1676-0611-BN-2025-1870\n"
            "Abstract\nThis study reports bryophyte species.\n"
            "Resumo\nEste estudo relata espécies de briófitas.\n"
            "Keywords: Amazon flora; Herbarium\n"
            "Palavras-chave: Flora amazônica; Herbário\n"
            "FAPESP 2024/23894-1"
        ),
    },
    {
        "role": "assistant",
        "content": (
            '{"article_ids":[{"pub_id_type":"doi",'
            '"value":"10.1590/1676-0611-BN-2025-1870"}],'
            '"journal":{"journal_title":"Biota Neotropica",'
            '"issns":[{"pub_type":"epub","value":"1676-0611"}]},'
            '"titles":[{"kind":"main","text":"What do scientific collections reveal '
            'about the past of the Amazon?"},'
            '{"kind":"translated","language":"pt",'
            '"text":"O que as coleções científicas revelam sobre o passado da Amazônia?"}],'
            '"authors":[{"contrib_type":"author","given_names":"Jéssica S. de",'
            '"surname":"Lima","orcid":"0000-0002-3193-9315",'
            '"affiliations":["aff1"],"corresp":true}],'
            '"affiliations":[{"id":"aff1","label":"1",'
            '"orgname":"Instituto de Pesquisas Ambientais",'
            '"city":"São Paulo","state":"SP","country":"Brasil","country_code":"BR"}],'
            '"author_notes":{"corresp":"* Correspondence: jessica@example.com"},'
            '"history":[{"type":"received","day":"10","month":"01","year":"2025"},'
            '{"type":"accepted","day":"21","month":"04","year":"2026"}],'
            '"abstracts":[{"kind":"main","title":"Abstract",'
            '"text":"This study reports bryophyte species."},'
            '{"kind":"translated","language":"pt","title":"Resumo",'
            '"text":"Este estudo relata espécies de briófitas."}],'
            '"keywords":[{"language":"en","title":"Keywords",'
            '"keywords":["Amazon flora","Herbarium"]},'
            '{"language":"pt","title":"Palavras-chave",'
            '"keywords":["Flora amazônica","Herbário"]}],'
            '"funding":{"awards":[{"funding_source":"FAPESP",'
            '"award_id":"2024/23894-1"}]}}'
        ),
    },
]

RESPONSE_FORMAT = {"type": "json_object"}

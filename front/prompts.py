MESSAGES = [
    {
        "role": "system",
        "content": (
            "You extract SciELO SPS 1.10 <front> metadata from article front matter. "
            "Respond ONLY with one JSON object. Omit keys that are not in the text. "
            "Never write the strings null, None, or undefined; omit the key instead. "
            "Never invent DOI, ISSN, ORCID, dates, volume, issue, pages, funding, "
            "license, counts, publisher_name, keywords, or journal identifiers. Do "
            "not copy names, ORCID, DOI, ISSN, dates, or keywords from the "
            "example; use only this input. "
            "JSON keys: journal, article_ids, categories, titles, authors, "
            "affiliations, author_notes, pub_dates, volume, issue, fpage, lpage, "
            "elocation_id, abstracts, keywords, history, permissions, counts, funding. "
            "journal: journal_ids [{type: publisher-id|nlm-ta, value}], "
            "journal_title (masthead name only, before volume/issue, e.g. the first "
            "line Journal Name 26(2) -> Journal Name), "
            "abbrev_journal_title, issns [{pub_type: epub|ppub, value}]; "
            "emit every ISSN written: print/impresso/printed -> ppub, "
            "online/eletrônico/on-line -> epub; if only one and unlabeled, "
            "epub; never copy ISSN values from the example. "
            "publisher_name (omit if not written; never SciELO SPS). "
            "article_ids: [{pub_id_type: doi|publisher-id|other, value}]; doi is the "
            "bare id without https://doi.org/. "
            "categories: [{subj_group_type: heading, subject}] maps to "
            "<subj-group subj-group-type>; SciELO SPS type is always heading. "
            "subject is the article type near the title (Article, Original Article, "
            "Review, Short Communication, Artigo, Comunicação breve, etc.). "
            "Articles/Artigos as a section label maps to Article/Artigo. "
            "omit if none appears; do not default to Article. "
            "titles: [{kind: main|translated, text, language?}]; language only on "
            "translated. "
            "authors: [{contrib_type (default author), given_names, surname, collab, "
            "orcid (bare 0000-0000-0000-0000), affiliations [aff ids], corresp bool, "
            "roles []}]. "
            "Portuguese/Spanish particles (de, da, do, dos, das, del) go in "
            "given_names, never in surname: Dimas M. do Carmo -> given_names "
            '"Dimas M. do", surname "Carmo". '
            "corresp true only for the corresponding author marked in the text. "
            "ORCID belongs to the name it appears next to; copy every ORCID URL "
            "(http or https) from the ORCID list onto that author; omit only if "
            "that name has no ORCID. "
            "affiliations: [{id, label, original, orgname, orgdiv1, orgdiv2, city, "
            "state, postal_code, country, country_code (ISO 3166-1 alpha-2), email}]. "
            "city is the municipality, not campus, highway, or neighborhood; put "
            "campus or center in orgdiv1 or orgdiv2. "
            "author_notes: {corresp, fns:[{text}]}. "
            "pub_dates: [{type: pub|collection, day, month, year, season}]. "
            "history: [{type: received|rev-recd|accepted, day, month, year}]. "
            "Omit history entirely if Received/Recebido or Accepted/Aceito are "
            "absent; never fill day, month, or year with null. "
            "Use only dates written in this input (Received/Recebido/Recibido/"
            "Submitted, Accepted/Aceito/Aceptado/Aprovado/Accepted for "
            "publication, Revised/Revisado). Numeric dates are day/month/year, "
            "never month/day: 22/12/2025 is day 22, month 12, year 2025, not "
            "January; 07/03/2024 is day 07, month 03, year 2024, not July; "
            "23 09 2025 is day 23, month 09. Also parse 23 Sept. 2025, "
            "09 Dec. 2025, 23 de setembro de 2025, 18 June 2025, and "
            "July 07, 2025. Always emit numeric month 01-12 (Sept/setembro=09, "
            "Dec/dezembro=12). Pad day and month as 01-31 and 01-12. "
            "abstracts: omit this key; Abstract/Resumo/Resumen paragraphs are "
            "copied from the source. Never paste abstract text into JSON. "
            "Keep the JSON compact. "
            "keywords: [{language, title, keywords:[]}]; one string per term; "
            "split only on semicolons (a comma stays inside the term); never "
            "one string with all terms and never join terms without separators; "
            "a multi-word phrase is one term (Violence against Women); emit a "
            "group only for headings in the text (Keywords, Palavras-chave, "
            "Palabras clave); do not add a language or term that is not written; "
            "keep capitalization as written. "
            "permissions: {copyright_statement, copyright_year, copyright_holder, "
            "license_href, license_p}. "
            "counts: {fig_count, table_count, equation_count, ref_count} as strings "
            "only when stated. "
            "funding: {awards:[{funding_source, award_id}], funding_statement} "
            "when FAPESP, CNPq, CAPES, Processo, or Grant appears; omit if absent."
        ),
    },
    {
        "role": "user",
        "content": (
            "Revista Exemplo de Ciências 12(3): e20240099, 2024\n"
            "www.scielo.br/rec\n"
            "ISSN 1111-2222 (Print)\n"
            "ISSN 3333-4444 (Online)\n"
            "Original Article\n"
            "Seasonal rainfall and forest birds in the Cerrado\n"
            "Chuva sazonal e aves florestais no Cerrado\n"
            "Ana P. da Silva https://orcid.org/0000-0001-1111-1111\n"
            "Carlos R. do Nascimento https://orcid.org/0000-0002-2222-2222\n"
            "1 Universidade Federal de Sample, Instituto de Biologia, São Paulo, "
            "SP, Brasil.\n"
            "2 Universidade Estadual de Sample, Campus do Interior, Rod. ABC km 4, "
            "Itirapina, SP, Brasil.\n"
            "* Correspondence: ana@example.com\n"
            "Received: 07/03/2024. Accepted: 18/11/2024.\n"
            "DOI: 10.1590/rec-2024-0099\n"
            "Abstract\nBird counts increased after late rains.\n"
            "Resumo\nA contagem de aves aumentou após as chuvas tardias.\n"
            "Keywords: Seasonal rainfall; Forest birds; Cerrado; "
            "Bioindicators; Conservation\n"
            "Palavras-chave: Chuva sazonal; Aves florestais; Cerrado; "
            "Bioindicadores; Conservação\n"
            "CNPq 312345/2023-0"
        ),
    },
    {
        "role": "assistant",
        "content": (
            '{"article_ids":[{"pub_id_type":"doi","value":"10.1590/rec-2024-0099"}],'
            '"journal":{"journal_title":"Revista Exemplo de Ciências",'
            '"issns":[{"pub_type":"ppub","value":"1111-2222"},'
            '{"pub_type":"epub","value":"3333-4444"}]},'
            '"categories":[{"subj_group_type":"heading",'
            '"subject":"Original Article"}],'
            '"titles":[{"kind":"main","text":"Seasonal rainfall and forest birds in '
            'the Cerrado"},'
            '{"kind":"translated","language":"pt",'
            '"text":"Chuva sazonal e aves florestais no Cerrado"}],'
            '"authors":[{"contrib_type":"author","given_names":"Ana P. da",'
            '"surname":"Silva","orcid":"0000-0001-1111-1111",'
            '"affiliations":["aff1"],"corresp":true},'
            '{"contrib_type":"author","given_names":"Carlos R. do",'
            '"surname":"Nascimento","orcid":"0000-0002-2222-2222",'
            '"affiliations":["aff2"]}],'
            '"affiliations":[{"id":"aff1","label":"1",'
            '"orgname":"Universidade Federal de Sample",'
            '"orgdiv1":"Instituto de Biologia",'
            '"city":"São Paulo","state":"SP","country":"Brasil","country_code":"BR"},'
            '{"id":"aff2","label":"2",'
            '"orgname":"Universidade Estadual de Sample",'
            '"orgdiv1":"Campus do Interior",'
            '"city":"Itirapina","state":"SP","country":"Brasil","country_code":"BR"}],'
            '"author_notes":{"corresp":"* Correspondence: ana@example.com"},'
            '"history":[{"type":"received","day":"07","month":"03","year":"2024"},'
            '{"type":"accepted","day":"18","month":"11","year":"2024"}],'
            '"keywords":[{"language":"en","title":"Keywords",'
            '"keywords":["Seasonal rainfall","Forest birds","Cerrado",'
            '"Bioindicators","Conservation"]},'
            '{"language":"pt","title":"Palavras-chave",'
            '"keywords":["Chuva sazonal","Aves florestais","Cerrado",'
            '"Bioindicadores","Conservação"]}],'
            '"funding":{"awards":[{"funding_source":"CNPq",'
            '"award_id":"312345/2023-0"}]}}'
        ),
    },
]

RESPONSE_FORMAT = {"type": "json_object"}

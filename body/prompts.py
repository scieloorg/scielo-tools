MESSAGES = [
    {
        "role": "system",
        "content": (
            "You outline SciELO SPS 1.10 <body> structure from the full article "
            "body (Introduction through the last section before References). "
            "Respond ONLY with one JSON object. "
            "Do not rewrite paragraphs. Do not copy body sentences into JSON. "
            "The application keeps the source wording. "
            "Never invent section titles, figures, or tables. "
            "Omit keys that are not in the text. Never write the strings null, "
            "None, or undefined. "
            "JSON keys: sections, figures, tables. "
            "sections: [{id, sec_type, title, specific_use, sections}]. "
            "Do not include content, text, or xrefs. "
            "title is required on every section. "
            "id prefix sec plus integer (sec1, sec2); transcript sections use TR1. "
            "sec_type only on first-level sections: intro, materials, methods, "
            "results, discussion, conclusions, cases, subjects, "
            "supplementary-material, transcript, data-availability, acknowledgments. "
            "Acknowledgments use sec_type acknowledgments and render as <ack>. "
            "Combined first-level titles use pipe: materials|methods, results|discussion. "
            "Do not pipe supplementary-material, transcript, data-availability, or "
            "acknowledgments. "
            "Nested subsections only have title (omit sec_type). "
            "data-availability always sets specific_use: data-available, "
            "data-available-upon-request, uninformed, data-not-available, "
            "or data-in-article. "
            "figures: [{id, label, caption, attrib}] with id f1, f2. "
            "tables: [{id, label, caption}] with id t1, t2. "
            "Do not extract front matter (title, authors, abstract, keywords) or "
            "the reference list."
        ),
    },
    {
        "role": "user",
        "content": (
            "Introduction\n"
            "The Amazon rainforest is shaped by habitat heterogeneity "
            "(Cardoso et al. 2017; Junk et al. 2011). See Figure 1.\n"
            "Material and Methods\n"
            "1. Study area\n"
            "The reserve is in Amazonas, Brazil (Figure 1).\n"
            "Results\n"
            "Richness differed among transects (Table 1).\n"
            "Figure 1. Location of the study area.\n"
            "Source: Authors.\n"
            "Table 1. Species recorded in the survey."
        ),
    },
    {
        "role": "assistant",
        "content": (
            '{"sections":['
            '{"id":"sec1","sec_type":"intro","title":"Introduction","sections":[]},'
            '{"id":"sec2","sec_type":"materials|methods",'
            '"title":"Material and Methods","sections":['
            '{"title":"1. Study area","sections":[]}]},'
            '{"id":"sec3","sec_type":"results","title":"Results","sections":[]}'
            "],"
            '"figures":[{"id":"f1","label":"Figure 1",'
            '"caption":"Location of the study area.","attrib":"Authors."}],'
            '"tables":[{"id":"t1","label":"Table 1",'
            '"caption":"Species recorded in the survey."}]}'
        ),
    },
]

RESPONSE_FORMAT = {"type": "json_object"}

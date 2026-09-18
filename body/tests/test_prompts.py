from body.prompts import MESSAGES, RESPONSE_FORMAT


def test_prompt_instructs_sps_body_contract():
    system = MESSAGES[0]["content"]
    assert "SciELO SPS 1.10 <body>" in system
    assert "Do not rewrite paragraphs" in system
    assert "Do not copy body sentences" in system
    assert "Do not include content, text, or xrefs" in system
    assert "sec_type" in system
    assert "materials|methods" in system
    assert "results|discussion" in system
    assert "Do not pipe supplementary-material" in system
    assert "acknowledgments" in system
    assert "always sets specific_use" in system
    assert "f1" in system
    assert "t1" in system
    assert "Do not extract front matter" in system
    assert RESPONSE_FORMAT == {"type": "json_object"}
    assert "materials|methods" in MESSAGES[2]["content"]
    assert "content" not in MESSAGES[2]["content"]
    assert "Cardoso et al. 2017" not in MESSAGES[2]["content"]

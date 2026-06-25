from spsvalidator.web.i18n import get_translations, normalize_language


def test_normalize_language_defaults_to_portuguese():
    assert normalize_language(None) == "pt"
    assert normalize_language("en-US") == "en"
    assert normalize_language("xx") == "pt"


def test_translations_available_for_all_languages():
    for language in ("pt", "en", "es"):
        translations = get_translations(language)
        assert translations["validate_package"]
        assert translations["footer_built_for_macos"]

from app.languages import (
    display_language,
    native_name,
    normalize_language,
    parse_query,
    resolve_target,
    suggest_language,
    to_language_code,
)


def test_parse_query_no_prefix():
    assert parse_query("hello world") == (None, "hello world")


def test_parse_query_code_prefix():
    assert parse_query("fr: bonjour le monde") == ("French", "bonjour le monde")


def test_parse_query_name_prefix():
    assert parse_query("Spanish: good morning") == ("Spanish", "good morning")


def test_parse_query_unknown_prefix_is_not_a_prefix():
    # An ordinary colon must not be mistaken for a language override.
    assert parse_query("Note: buy milk") == (None, "Note: buy milk")


def test_parse_query_colon_in_body_preserved():
    target, body = parse_query("de: Zeit: 10:30 Uhr")
    assert target == "German"
    assert body == "Zeit: 10:30 Uhr"


def test_parse_query_prefix_only_no_body():
    assert parse_query("fr:") == (None, "fr:")


def test_parse_query_strips_surrounding_whitespace():
    assert parse_query("  ru :  привет  ") == ("Russian", "привет")


def test_parse_query_multiline_body():
    target, body = parse_query("ja: line one\nline two")
    assert target == "Japanese"
    assert body == "line one\nline two"


def test_normalize_language():
    assert normalize_language("FR") == "French"
    assert normalize_language("german") == "German"
    assert normalize_language("klingon") is None


def test_normalize_language_accepts_aliases():
    assert normalize_language("farsi") == "Persian"
    assert normalize_language("mandarin") == "Chinese"


def test_normalize_language_accepts_native_names():
    assert normalize_language("Українська") == "Ukrainian"
    assert normalize_language("Español") == "Spanish"
    assert normalize_language("日本語") == "Japanese"


def test_native_name():
    assert native_name("Ukrainian") == "Українська"
    assert native_name("uk") == "Українська"
    assert native_name("not a language") is None


def test_display_language():
    assert display_language("Ukrainian") == "Ukrainian (Українська)"
    assert display_language("es") == "Spanish (Español)"
    # No parenthetical when the native name matches the English name.
    assert display_language("English") == "English"
    # Unknown values pass through unchanged.
    assert display_language("Klingon") == "Klingon"


def test_resolve_target_canonicalizes_known():
    assert resolve_target("es") == "Spanish"
    assert resolve_target("Russian") == "Russian"


def test_resolve_target_covers_well_known_languages():
    # Languages beyond the most common handful still resolve exactly.
    assert resolve_target("swahili") == "Swahili"
    assert resolve_target("Zulu") == "Zulu"


def test_resolve_target_rejects_unknown_and_garbage():
    assert resolve_target("Ukraini") is None  # near-miss -> suggestions instead
    assert resolve_target("123!!!") is None
    assert resolve_target("") is None


def test_to_language_code():
    assert to_language_code("Chinese") == "zh"
    assert to_language_code("uk") == "uk"
    assert to_language_code("Ukrainian") == "uk"
    assert to_language_code("not a language") is None


def test_to_language_code_accepts_native_names():
    assert to_language_code("Español") == "es"
    assert to_language_code("Українська") == "uk"


def test_suggest_language_matches_native_spelling():
    assert "Spanish" in suggest_language("Españ")


def test_suggest_language_prefix():
    # A truncated word resolves to its language, listed first.
    assert suggest_language("Chi")[0] == "Chinese"
    assert suggest_language("Ukraini")[0] == "Ukrainian"
    assert suggest_language("Portu")[0] == "Portuguese"


def test_suggest_language_typo():
    assert "Ukrainian" in suggest_language("Ukrannian")


def test_suggest_language_no_match():
    assert suggest_language("xyzzy") == []
    assert suggest_language("z") == []


def test_suggest_language_caps_at_three():
    assert len(suggest_language("an")) <= 3

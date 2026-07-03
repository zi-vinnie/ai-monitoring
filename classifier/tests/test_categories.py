from classifier.categories import CATEGORIES, LABEL_FORMAT, build_prompt, parse_label


def test_parse_label_from_structured_json():
    assert parse_label('{"label": "gaming"}') == "gaming"


def test_parse_label_from_json_with_whitespace():
    assert parse_label('  {"label":"idle_locked"}\n') == "idle_locked"


def test_parse_label_rejects_unknown_json_label():
    # Valid JSON but not one of our categories, and no category name appears in
    # the text either -> unclassifiable.
    assert parse_label('{"label": "cooking"}') is None


def test_parse_label_falls_back_to_substring():
    # A model that ignored the format and replied in prose still resolves.
    assert parse_label("This looks like social_media to me.") == "social_media"


def test_parse_label_empty_is_none():
    assert parse_label("") is None
    assert parse_label("   ") is None


def test_label_format_enum_matches_categories():
    assert LABEL_FORMAT["properties"]["label"]["enum"] == list(CATEGORIES)


def test_build_prompt_includes_window_title_hint():
    prompt = build_prompt("Rocket League")
    assert "Rocket League" in prompt
    assert "gaming" in prompt


def test_build_prompt_handles_missing_title():
    prompt = build_prompt(None)
    assert "no focused-window title" in prompt

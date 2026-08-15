from src.services.import_export_service import (
    collapse_whitespace,
    escape_field,
    extract_card_text,
    is_custom_separator_valid,
    parse_text_import,
    resolve_delimiter,
    resolve_record_separator,
    serialize_text_export,
    tokenize_text,
)


def test_resolve_separators():
    assert resolve_delimiter("tab") == "\t"
    assert resolve_delimiter("comma") == ","
    assert resolve_delimiter("custom", " | ") == " | "
    assert resolve_record_separator("newline") == "\n"
    assert resolve_record_separator("semicolon") == ";"
    assert resolve_record_separator("custom", "|||") == "|||"
    assert not is_custom_separator_valid("")
    assert not is_custom_separator_valid(None)
    assert is_custom_separator_valid(" ")
    assert is_custom_separator_valid("~")


def test_extract_card_text():
    elements = [
        {"type": "text", "content": "Hello"},
        {"type": "image", "url": "https://example.com/img.png"},
        {"type": "text", "content": "World"},
    ]
    assert extract_card_text(elements) == "Hello World"
    assert extract_card_text([]) == ""
    assert extract_card_text(None) == ""


def test_parse_text_import_tab_newline():
    text = "front1\tback1\nfront2\tback2"
    cards, skipped, total = parse_text_import(text, "tab", "newline")
    assert len(cards) == 2
    assert skipped == 0
    assert total == 2
    assert cards[0] == ("front1", "back1")
    assert cards[1] == ("front2", "back2")


def test_parse_text_import_crlf_and_skipped():
    text = "a\tb\r\n\r\nc\td\r\nnodelim\r\n\tdangling"
    cards, skipped, total = parse_text_import(text, "tab", "newline")
    assert len(cards) == 2
    assert skipped == 2
    assert total == 4
    assert cards[0] == ("a", "b")
    assert cards[1] == ("c", "d")


def test_parse_text_import_comma_with_inner_commas():
    text = "Q,answer,with,commas\nQ2,b"
    cards, skipped, total = parse_text_import(text, "comma", "newline")
    assert len(cards) == 2
    assert cards[0] == ("Q", "answer,with,commas")
    assert cards[1] == ("Q2", "b")


def test_parse_text_import_semicolon_custom_delim():
    text = "Q1 :: A1; Q2 :: A2"
    cards, skipped, total = parse_text_import(
        text, "custom", "semicolon", custom_delim=" ::"
    )
    assert len(cards) == 2
    assert cards[0] == ("Q1", "A1")
    assert cards[1] == ("Q2", "A2")


def test_parse_text_import_csv_quoting():
    text = '"front, with comma"\tback\nfront2\t"back with ""doubled quotes"""'
    cards, skipped, total = parse_text_import(text, "tab", "newline")
    assert len(cards) == 2
    assert cards[0] == ("front, with comma", "back")
    assert cards[1] == ("front2", 'back with "doubled quotes"')


def test_parse_text_import_multiline_quotes():
    text = '"front\nmulti\nline"\t"back\nline2"'
    cards, skipped, total = parse_text_import(text, "tab", "newline")
    assert len(cards) == 1
    assert cards[0] == ("front\nmulti\nline", "back\nline2")


def test_serialize_text_export_roundtrip():
    cards = [
        ("front one", "back one"),
        ("line one\nline two", "back\nwith\n\nseveral lines"),
        ("front, with comma", 'back "with" quotes and , comma'),
    ]
    exported = serialize_text_export(cards, "tab", "newline")
    assert "front one\tback one" in exported

    reimported, skipped, total = parse_text_import(exported, "tab", "newline")
    assert len(reimported) == 3
    assert reimported[0] == ("front one", "back one")
    assert reimported[1] == ("line one line two", "back with several lines")
    assert reimported[2] == ("front, with comma", 'back "with" quotes and , comma')

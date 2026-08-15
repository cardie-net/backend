import re
from typing import Any, Literal

DelimiterKind = Literal["tab", "comma", "custom"]
RecordSeparatorKind = Literal["newline", "semicolon", "custom"]


def resolve_delimiter(kind: DelimiterKind, custom: str | None = None) -> str:
    """Resolve delimiter configuration to literal string."""
    if kind == "custom":
        return custom if custom is not None else ""
    return "\t" if kind == "tab" else ","


def resolve_record_separator(
    kind: RecordSeparatorKind, custom: str | None = None
) -> str:
    """Resolve record separator configuration to literal string."""
    if kind == "custom":
        return custom if custom is not None else ""
    return "\n" if kind == "newline" else ";"


def is_custom_separator_valid(value: str | None) -> bool:
    """Check if custom separator is non-empty."""
    return bool(value and len(value) > 0)


def extract_card_text(elements: list[Any] | None) -> str:
    """Extract text from card elements list, discarding non-text elements."""
    if not elements:
        return ""
    parts: list[str] = []
    for el in elements:
        if isinstance(el, dict):
            if el.get("type") == "text":
                parts.append(str(el.get("content", "")))
        else:
            if getattr(el, "type", None) == "text":
                parts.append(str(getattr(el, "content", "")))
    return " ".join(parts)


def tokenize_text(text: str, delim: str, sep: str) -> list[list[str]]:
    """Single-pass quote-aware tokenizer (RFC-4180 style)."""
    records: list[list[str]] = []
    fields: list[str] = []
    field_chars: list[str] = []
    in_quotes = False
    i = 0
    n = len(text)

    def end_field() -> None:
        nonlocal field_chars
        fields.append("".join(field_chars))
        field_chars = []

    def end_record() -> None:
        nonlocal fields
        end_field()
        records.append(fields)
        fields = []

    while i < n:
        if in_quotes:
            if text[i] == '"':
                if i + 1 < n and text[i + 1] == '"':
                    field_chars.append('"')
                    i += 2
                    continue
                in_quotes = False
                i += 1
                continue
            field_chars.append(text[i])
            i += 1
            continue

        if text.startswith(sep, i):
            end_record()
            i += len(sep)
            continue
        if len(field_chars) == 0 and text[i] == '"':
            in_quotes = True
            i += 1
            continue
        if text.startswith(delim, i):
            end_field()
            i += len(delim)
            continue
        field_chars.append(text[i])
        i += 1

    end_record()
    return records


def parse_text_import(
    text: str,
    delim_kind: DelimiterKind = "tab",
    sep_kind: RecordSeparatorKind = "newline",
    custom_delim: str | None = None,
    custom_sep: str | None = None,
) -> tuple[list[tuple[str, str]], int, int]:
    """Parse text into (front, back) card tuples, skipped count, and total count."""
    delim = resolve_delimiter(delim_kind, custom_delim)
    sep = resolve_record_separator(sep_kind, custom_sep)
    if not delim or not sep:
        return [], 0, 0

    normalized = text.replace("\r\n", "\n").replace("\r", "\n") if sep == "\n" else text
    records = tokenize_text(normalized, delim, sep)

    cards: list[tuple[str, str]] = []
    skipped = 0
    total = 0

    for raw_fields in records:
        if len(raw_fields) <= 1 and (not raw_fields or not raw_fields[0].strip()):
            continue
        total += 1

        front = raw_fields[0].strip() if raw_fields else ""
        if len(raw_fields) < 2 or not front:
            skipped += 1
            continue

        back = delim.join(raw_fields[1:]).strip()
        cards.append((front, back))

    return cards, skipped, total


def collapse_whitespace(value: str) -> str:
    """Collapse consecutive whitespace into single space and trim ends."""
    return re.sub(r"\s+", " ", value).strip()


def escape_field(value: str, delim: str, sep: str) -> str:
    """CSV-style quote escaping when value contains delimiter, separator, or quote."""
    if delim not in value and sep not in value and '"' not in value:
        return value
    escaped = value.replace('"', '""')
    return f'"{escaped}"'


def serialize_text_export(
    cards_data: list[tuple[str, str]],
    delim_kind: DelimiterKind = "tab",
    sep_kind: RecordSeparatorKind = "newline",
    custom_delim: str | None = None,
    custom_sep: str | None = None,
) -> str:
    """Serialize front/back text cards to delimited format."""
    delim = resolve_delimiter(delim_kind, custom_delim)
    sep = resolve_record_separator(sep_kind, custom_sep)
    if not delim or not sep:
        return ""

    rows: list[str] = []
    for front, back in cards_data:
        front_clean = collapse_whitespace(front)
        back_clean = collapse_whitespace(back)
        if not front_clean:
            continue
        front_escaped = escape_field(front_clean, delim, sep)
        back_escaped = escape_field(back_clean, delim, sep)
        rows.append(f"{front_escaped}{delim}{back_escaped}")

    return sep.join(rows)

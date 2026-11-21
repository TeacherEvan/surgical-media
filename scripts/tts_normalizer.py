#!/usr/bin/env python3
"""tts_normalizer.py -- deterministic text normalization for local TTS.

Local voices (e.g. Kokoro) misread numeric dates, currency amounts and
hashtags. This module rewrites those tokens into natural spoken English
*before* synthesis. It is stdlib-only, offline and fully deterministic: the
same input always produces the same output.

Two entry points:

* :func:`normalize_text` normalizes a single string.
* :func:`normalize_script` walks a JSON tree and normalizes only string values
  stored under ``narration`` or ``text`` keys, returning the new tree and a
  change log.

CLI::

    python3 scripts/tts_normalizer.py --input script.json \
        --output script.spoken.json --report normalization.json
    python3 scripts/tts_normalizer.py --text "Meta raised $3.2B on 2026-11-21 #AI" --emit-text
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_ONES: list[str] = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS: list[str] = [
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
]
_SCALES: tuple[tuple[str, int], ...] = (
    ("trillion", 10**12),
    ("billion", 10**9),
    ("million", 10**6),
    ("thousand", 10**3),
)
_MONTHS: tuple[str, ...] = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_WORD_ORDINAL: dict[str, str] = {
    "one": "first",
    "two": "second",
    "three": "third",
    "four": "fourth",
    "five": "fifth",
    "six": "sixth",
    "seven": "seventh",
    "eight": "eighth",
    "nine": "ninth",
    "ten": "tenth",
    "eleven": "eleventh",
    "twelve": "twelfth",
    "thirteen": "thirteenth",
    "fourteen": "fourteenth",
    "fifteen": "fifteenth",
    "sixteen": "sixteenth",
    "seventeen": "seventeenth",
    "eighteen": "eighteenth",
    "nineteen": "nineteenth",
    "twenty": "twentieth",
    "thirty": "thirtieth",
    "forty": "fortieth",
    "fifty": "fiftieth",
    "sixty": "sixtieth",
    "seventy": "seventieth",
    "eighty": "eightieth",
    "ninety": "ninetieth",
}
_SCALE_CHARS: dict[str, str] = {
    "B": "billion",
    "M": "million",
    "K": "thousand",
}
_TARGET_KEYS: frozenset[str] = frozenset({"narration", "text"})

# Word-boundary aware token regex. Order matters: the most specific patterns
# come first so a date is never re-read as a bare year/number, and URLs are
# consumed whole before anything inside them can be touched.
_TOKEN_RE: re.Pattern[str] = re.compile(
    r"(?P<url>https?://\S+)"
    r"|(?P<iso_date>\b\d{4}-\d{2}-\d{2}\b)"
    r"|(?P<us_date>\b\d{1,2}/\d{1,2}/\d{4}\b)"
    r"|(?P<currency>[$R]\d[\d,]*(?:\.\d+)?[BMKbmk]?)"
    r"|(?P<percent>\b\d[\d,]*(?:\.\d+)?%)"
    r"|(?P<ordinal>\b\d+(?:st|nd|rd|th)\b)"
    r"|(?P<hashtag>#[A-Za-z][A-Za-z0-9]*)"
    r"|(?P<mention>@[A-Za-z][A-Za-z0-9_]*)"
    r"|(?P<comma_num>\b\d{1,3}(?:,\d{3})+\b)"
    r"|(?P<decimal>\b\d+\.\d+\b)"
    r"|(?P<year>\b\d{4}\b)"
    r"|(?P<number>\b\d+\b)"
)


def _tens_and_units(n: int) -> str:
    """Spell an integer in [0, 99] with space-separated words."""
    if n < 20:
        return _ONES[n]
    tens = n // 10
    rem = n % 10
    word = _TENS[tens]
    return word + (f" {_ONES[rem]}" if rem else "")


def number_to_words(n: int) -> str:
    """Spell an integer using space-separated English words (no hyphens).

    >>> number_to_words(42)
    'forty two'
    >>> number_to_words(1200)
    'one thousand two hundred'
    """
    if n < 0:
        return "minus " + number_to_words(-n)
    if n < 100:
        return _tens_and_units(n)
    if n < 1000:
        head = _ONES[n // 100] + " hundred"
        rem = n % 100
        return head + (f" {_tens_and_units(rem)}" if rem else "")
    for scale, divisor in _SCALES:
        if n >= divisor:
            head = number_to_words(n // divisor)
            rem = n % divisor
            out = f"{head} {scale}"
            return out + (f" {number_to_words(rem)}" if rem else "")
    return str(n)


def year_to_words(year: int) -> str:
    """Spell a four-digit year the way English speakers read it aloud.

    ``2026 -> 'twenty twenty six'``, ``1984 -> 'nineteen eighty four'``,
    ``2000 -> 'two thousand'``, ``2010 -> 'twenty ten'``.
    """
    if year == 2000:
        return "two thousand"
    if 2001 <= year <= 2009:
        return f"two thousand {_ONES[year - 2000]}"
    if 2010 <= year <= 2099:
        return f"twenty {_tens_and_units(year % 100)}"
    if 1900 <= year <= 1999:
        last = year % 100
        if last == 0:
            return "nineteen hundred"
        if last < 10:
            return f"nineteen oh {_ONES[last]}"
        return f"nineteen {_tens_and_units(last)}"
    return number_to_words(year)


def ordinal_to_words(n: int) -> str:
    """Spell an ordinal number, e.g. 1 -> 'first', 21 -> 'twenty first'."""
    words = number_to_words(n)
    last = words.rsplit(" ", 1)[-1]
    replacement = _WORD_ORDINAL.get(last)
    if replacement is None:
        return words + "th"
    head = words[: len(words) - len(last)]
    return (head + replacement).strip()


def _amount_to_words(token: str) -> str:
    """Spell a numeric amount with an optional decimal part (digit-by-digit)."""
    token = token.replace(",", "")
    if "." in token:
        whole, frac = token.split(".", 1)
        head = number_to_words(int(whole)) if whole else "zero"
        digits = " ".join(_ONES[int(digit)] for digit in frac)
        return head + " point " + digits
    return number_to_words(int(token))


def _currency_to_words(token: str) -> str:
    """Spell a ``$``/``R`` currency token, including B/M/K suffixes."""
    scale_char = ""
    if token[-1].upper() in _SCALE_CHARS:
        scale_char = token[-1].upper()
        token = token[:-1]
    currency = "rand" if token.startswith("R") else "dollars"
    if token[0] in "$R":
        token = token[1:]
    parts = [_amount_to_words(token)]
    if scale_char:
        parts.append(_SCALE_CHARS[scale_char])
    parts.append(currency)
    return " ".join(parts)


def _split_camel(name: str) -> str:
    """Turn a hashtag body into spoken words.

    All-caps acronyms are spelled letter by letter (``AI -> 'A I'``);
    CamelCase names are split at case boundaries (``BigTech -> 'Big Tech'``).
    """
    if name.isupper():
        return " ".join(name)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    return spaced


def _format_date(month: int, day: int, year: int, original: str) -> str:
    """Render a date as 'Month day-ordinal, year', or keep an invalid token."""
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return original
    return f"{_MONTHS[month]} {ordinal_to_words(day)}, {year_to_words(year)}"


def _replace(match: re.Match[str]) -> str:
    """Substitution callback: dispatch a token to its normalizer."""
    if match.group("url") is not None:
        return match.group(0)  # never damage URLs

    token = match.group(0)

    value = match.group("iso_date")
    if value is not None:
        return _format_date(int(value[5:7]), int(value[8:10]), int(value[:4]), token)

    value = match.group("us_date")
    if value is not None:
        month, day, year = (int(part) for part in value.split("/"))
        return _format_date(month, day, year, token)

    value = match.group("currency")
    if value is not None:
        return _currency_to_words(value)

    value = match.group("percent")
    if value is not None:
        return f"{_amount_to_words(value[:-1])} percent"

    value = match.group("ordinal")
    if value is not None:
        return ordinal_to_words(int(value[:-2]))

    value = match.group("hashtag")
    if value is not None:
        return "hash " + _split_camel(value[1:])

    value = match.group("mention")
    if value is not None:
        return "at " + value[1:]

    value = match.group("comma_num")
    if value is not None:
        return number_to_words(int(value.replace(",", "")))

    value = match.group("decimal")
    if value is not None:
        return _amount_to_words(value)

    value = match.group("year")
    if value is not None:
        return year_to_words(int(value))

    value = match.group("number")
    if value is not None:
        return number_to_words(int(value))

    return token


def normalize_text(text: str) -> str:
    """Normalize one string, expanding spoken-unfriendly tokens into words."""
    if not text:
        return text
    result = _TOKEN_RE.sub(_replace, text)
    # Token rewrites are single-spaced; collapse any pre-existing runs too so
    # the output can never contain double spaces.
    return re.sub(r"[ \t]{2,}", " ", result)


def _walk(
    value: Any,
    path: str,
    key: str | None,
    changes: list[dict[str, str]],
) -> Any:
    """Recursively rebuild ``value``; record changes for narration/text strs."""
    if isinstance(value, dict):
        rebuilt: dict[str, Any] = {}
        for raw_key, child in value.items():
            child_key = str(raw_key)
            child_path = f"{path}/{child_key}" if path else child_key
            rebuilt[child_key] = _walk(child, child_path, child_key, changes)
        return rebuilt
    if isinstance(value, list):
        return [
            _walk(item, f"{path}/{i}" if path else str(i), key, changes)
            for i, item in enumerate(value)
        ]
    if isinstance(value, str) and key is not None and key in _TARGET_KEYS:
        normalized = normalize_text(value)
        if normalized != value:
            changes.append({"path": path, "before": value, "after": normalized})
        return normalized
    return value


def normalize_script(data: Any) -> tuple[Any, list[dict[str, str]]]:
    """Normalize narration/text strings anywhere in a JSON-like tree.

    Returns ``(normalized_data, changes)`` where ``changes`` is a list of
    ``{"path", "before", "after"}`` records for values that actually changed.
    All other keys, values and structure are preserved.
    """
    changes: list[dict[str, str]] = []
    return _walk(data, "", None, changes), changes


def main(argv: list[str] | None = None) -> int:
    """Command line entry point. Returns 0 on success, 2 on bad input."""
    parser = argparse.ArgumentParser(
        description="Normalize numbers/dates/currency/hashtags for local TTS."
    )
    parser.add_argument("--input", type=Path, help="Input beat script JSON")
    parser.add_argument("--output", type=Path, help="Output normalized JSON")
    parser.add_argument("--report", type=Path, help="Optional JSON change log")
    parser.add_argument("--text", help="Inline text to normalize")
    parser.add_argument(
        "--emit-text",
        action="store_true",
        help="Print normalized inline text to stdout instead of JSON",
    )
    args = parser.parse_args(argv)

    if args.emit_text:
        if args.text is None:
            parser.error("--emit-text requires --text")
        print(normalize_text(args.text))
        return 0

    if args.text is not None and args.input is None:
        print(normalize_text(args.text))
        return 0

    if args.input is None or args.output is None:
        parser.error("--input and --output are required for JSON mode")

    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"tts_normalizer: cannot read script: {exc}", file=sys.stderr)
        return 2

    normalized, changes = normalize_script(data)

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(normalized, indent=2, ensure_ascii=False, sort_keys=False),
            encoding="utf-8",
        )
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(changes, indent=2, ensure_ascii=False, sort_keys=False),
                encoding="utf-8",
            )
    except OSError as exc:
        print(f"tts_normalizer: cannot write output: {exc}", file=sys.stderr)
        return 2

    if args.report is None:
        print(f"tts_normalizer: {len(changes)} change(s) written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

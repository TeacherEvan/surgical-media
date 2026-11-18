"""Unit tests for the code_terminal syntax tokenizer (elements/code.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from elements._shared import GOLD, GREEN, PURPLE
from elements.code import _syntax_tokens

DEFAULT = "#E5E9F0"
COMMENT = "#7D8590"


def as_map(text):
    return {seg: color for seg, color in _syntax_tokens(text, DEFAULT)}


def test_comment_is_gray():
    spans = _syntax_tokens("# hello world", DEFAULT)
    assert spans == [("# hello world", COMMENT)]


def test_python_comment_and_code_mix():
    spans = _syntax_tokens("x = 1  # tail", DEFAULT)
    assert ("# tail", COMMENT) in spans
    assert ("x", DEFAULT) in spans


def test_string_is_green():
    spans = _syntax_tokens('msg = "hi there"', DEFAULT)
    assert ('"hi there"', GREEN) in spans


def test_number_is_purple():
    spans = _syntax_tokens("total = 3.5", DEFAULT)
    assert ("3.5", PURPLE) in spans


def test_keyword_is_gold():
    spans = _syntax_tokens("return value", DEFAULT)
    assert ("return", GOLD) in spans
    assert ("value", DEFAULT) in spans


def test_string_and_comment_do_not_leak_into_each_other():
    spans = _syntax_tokens('x = "not // code"  # real comment', DEFAULT)
    assert ('"not // code"', GREEN) in spans
    assert ("# real comment", COMMENT) in spans


def test_empty_and_whitespace_lines():
    assert _syntax_tokens("", DEFAULT) == []
    assert _syntax_tokens("   ", DEFAULT) == [("   ", DEFAULT)]


def test_unterminated_string_still_tokens():
    # never throws on partial syntax; unmatched text keeps the default color
    spans = _syntax_tokens('msg = "oops', DEFAULT)
    assert "".join(seg for seg, _ in spans) == 'msg = "oops'
    assert all(color == DEFAULT for _, color in spans)

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pbs import textutil as T

VECTORS = json.loads((Path(__file__).parent / "vectors" / "text.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", VECTORS["x_length"], ids=lambda c: c["name"])
def test_x_weighted_length(case):
    assert T.x_weighted_length(case["text"]) == case["expected"]


@pytest.mark.parametrize("case", VECTORS["tokens"], ids=lambda c: c["name"])
def test_edit_tokens(case):
    assert T.edit_tokens(case["text"]) == case["expected"]


@pytest.mark.parametrize("case", VECTORS["edit_ratio"], ids=lambda c: c["name"])
def test_edit_ratio(case):
    assert T.edit_ratio(case["draft"], case["final"]) == pytest.approx(case["expected"], abs=1e-4)


def test_myers_matches_lcs_definition():
    a = ["a", "b", "c", "d", "e", "f", "g"]
    b = ["a", "x", "c", "d", "y", "f", "g", "z"]
    # LCS = a c d f g (5) -> D = 7 + 8 - 10 = 5
    assert T.myers_distance(a, b) == 5


def test_canonical_url_strips_tracking_and_normalises():
    assert T.canonical_url("http://www.Example.com/path/?utm_source=x&b=2&a=1#frag") == "https://example.com/path?a=1&b=2"
    assert T.canonical_url("https://example.com/") == "https://example.com/"


def test_title_key_drops_publisher_suffix():
    assert T.title_key("Bihar launches new scheme for farmers - The Hindu") == "bihar launches new scheme for farmers"
    assert T.title_key("Short - X") == "short x"


def test_numeric_claims_cover_formats():
    text = "1/ Revenue grew 37% to $2.5 billion in 2024, up 3.5x. About 1,200 jobs. ₹2,000 crore, 1,23,456 people"
    claims = T.numeric_claims(text)
    for expected in ["37%", "$2.5 billion", "2024", "3.5x", "1,200", "₹2,000 crore", "1,23,456"]:
        assert expected in claims
    assert "1" not in claims  # thread numbering is ignored


def test_sim_tokens_keep_model_names_and_drop_stopwords():
    toks = T.sim_tokens("OpenAI releases GPT-5.1 agents for the enterprise")
    assert "gpt-5.1" in toks and "agent" in toks and "the" not in toks


def test_detect_lang():
    assert T.detect_lang("बिहार में नई योजना") == "hi"
    assert T.detect_lang("Bihar launches scheme") == "en"


def test_opening_and_truncate():
    assert T.opening("First line here. Second sentence.\nMore") == "First line here."
    assert T.truncate("word " * 50, 30).endswith("…")

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pbs import guardrails as G


def test_blocklist_matching_is_robust():
    terms = G.parse_terms("Acme Corp\n# comment\nZeta-Bank, ProjectX\n\n")
    assert terms == ["Acme Corp", "Zeta-Bank", "ProjectX"]
    text = "We worked with acme-corp and Acme Corp's team on projectx. ZetaBank too"
    assert G.find_terms(text, terms) == ["Acme Corp", "Zeta-Bank", "ProjectX"]
    assert G.find_terms("Acmeology is unrelated", terms) == []


def test_redaction():
    assert G.redact("We worked with acme corp on ProjectX.", ["Acme Corp", "ProjectX"]) == \
        "We worked with [redacted] on [redacted]."


def test_first_person_and_opinion_flags():
    text = "OpenAI released a model. I built a similar agent last year. My team saw gains. This matters."
    assert G.first_person_claims(text) == ["I built a similar agent last year.", "My team saw gains."]
    assert G.opinion_framing("I think this is big. The data says otherwise.") == ["I think this is big."]


def test_unsourced_numbers():
    assert G.unsourced_numbers("Revenue grew 37% to $2.5 billion in 2024 and 12 plants",
                               "revenue up 37 percent to 2.5 billion (2024)") == ["12"]
    assert G.unsourced_numbers("₹12,000 crore approved", "Cabinet approved ₹12,000 crore") == []


def test_sensitive_check_english_and_hindi():
    assert G.sensitive_check("Stampede at temple kills 12")[0]
    assert G.sensitive_check("पटना में हिंसा")[0]
    assert not G.sensitive_check("Bihar budget rises", "no issues")[0]


def test_phrase_hits_handle_symbols():
    assert G.phrase_hits("This is a game-changer. Agree? 🚀", ["game-changer", "agree?", "🚀", "delve"]) == \
        ["game-changer", "agree?", "🚀"]


def test_check_card_blocks_and_flags(settings):
    card = {"platform": "x", "format": "x_single", "mode": "external", "title": "t", "angle": "",
            "draft": {"text": "I built this at Acme Corp and it cut costs 45%. Agree?"}, "hooks": [], "flags": {}}
    res = G.check_card(card, settings=settings, blocklist=["Acme Corp"], evidence="nothing", avoid_phrases=[],
                       bait_phrases=["agree?"])
    assert res.blocked and res.flags["blocked"] == ["Acme Corp"]
    assert res.flags["unsourced"] == ["45%"]
    assert res.flags["first_person"] and res.flags["bait"] == ["agree?"]


def test_length_flags(settings):
    long_post = "x" * 300
    assert G.length_flags("x", "x_single", {"text": long_post}, settings) == ["Post is 300/280"]
    flags = G.length_flags("x", "x_thread", {"posts": ["a", "b"]}, settings)
    assert flags and "Thread has 2 posts" in flags[0]
    li = G.length_flags("linkedin", "li_text", {"text": ("word " * 60).strip() + ".\n\nMore."}, settings)
    assert any("fold" in f for f in li)


AI_TELL_VECTORS = json.loads((Path(__file__).parent / "vectors" / "ai_tells.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", AI_TELL_VECTORS["ai_tells"], ids=lambda c: c["name"])
def test_ai_tells_shared_vectors(case):
    assert sorted({t["kind"] for t in G.ai_tells(case["text"])}) == case["kinds"]


def test_ai_tells_say_where_each_one_is_in_reading_order():
    tells = G.ai_tells("In today's world, agents matter. It's not about speed, it's about trust.\n\n"
                                "Ultimately, trust wins.")
    assert [t["kind"] for t in tells] == ["opener", "contrast", "closer"]
    assert tells[1]["text"] == "It's not about speed, it's about trust."

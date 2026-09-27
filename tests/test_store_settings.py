from __future__ import annotations

import pytest

from pbs import settings as S
from pbs.store import Store


def test_store_roundtrip_sharding_and_deletion(tmp_path):
    root = tmp_path / "data"
    s = Store.open(root)
    s.insert("cards", {"id": "c1", "platform": "x", "status": "suggested", "draft": {"text": "hi"}, "explore": True,
                       "created_at": "2026-09-28T01:00:00Z"})
    s.insert("cards", {"id": "c2", "platform": "linkedin", "status": "posted", "created_at": "2026-10-02T01:00:00Z"})
    changed = s.save()
    assert "db/cards/2026-09.jsonl" in changed and "db/cards/2026-10.jsonl" in changed

    s2 = Store.open(root)
    c1 = s2.get("cards", "c1")
    assert c1["draft"] == {"text": "hi"} and c1["explore"] is True and c1["topic_id"] is None
    assert s2.save() == []  # nothing changed, nothing written

    s2.delete("cards", "c2")
    assert s2.save() == ["db/cards/2026-10.jsonl"]
    assert not (root / "db/cards/2026-10.jsonl").exists()

    line = (root / "db/cards/2026-09.jsonl").read_text().strip()
    assert line.startswith('{"created_at"') and "null" not in line  # sorted keys, no nulls


def test_store_rejects_unknown_columns(store):
    with pytest.raises(KeyError):
        store.insert("cards", {"id": "x", "bogus": 1})


def test_upsert_updates_only_given_columns(store):
    store.insert("requests", {"id": "r1", "query": "q", "status": "queued"})
    store.upsert("requests", {"id": "r1", "status": "done"})
    assert store.get("requests", "r1")["query"] == "q"


def test_settings_defaults_are_valid(settings):
    assert settings.slots("linkedin") == 3 and settings.slots("x") == 6
    assert abs(sum(settings.normalized_weights("x").values()) - 1) < 1e-9
    assert settings.pillar("linkedin", "receipts").mode == "interview"


def test_bad_override_is_dropped_not_fatal():
    s, warnings = S.load({"platforms": {"x": {"slots": 99}}, "display_name": "A"})
    assert s.slots("x") == 6 and s.display_name == "A"
    assert warnings and "platforms.x.slots" in warnings[0]


def test_validate_patch_is_strict():
    assert S.validate_patch({}, {"platforms": {"x": {"slotz": 3}}})[1].startswith("unknown setting")
    new, err = S.validate_patch({}, {"platforms": {"x": {"slots": 5}}})
    assert err is None and new == {"platforms": {"x": {"slots": 5}}}
    assert "unknown providers" in S.validate_patch({}, {"llm": {"routes": {"draft": ["nope"]}}})[1]
    # Open maps may grow (new pillar), but the pillar must be valid.
    new, err = S.validate_patch({}, {"strategy": {"x": {"sport": {"label": "Sport", "weight": 0.1,
                                                                   "formats": ["x_single"]}}}})
    assert err is None
    _, err = S.validate_patch({}, {"strategy": {"x": {"sport": {"label": "Sport", "weight": 0.1,
                                                                 "formats": ["li_text"]}}}})
    assert err and "not valid on x" in err


def test_none_in_patch_resets_to_default():
    new, err = S.validate_patch({"platforms": {"x": {"slots": 5}}}, {"platforms": {"x": {"slots": None}}})
    assert err is None
    s, _ = S.load(new)
    assert s.slots("x") == 6

from __future__ import annotations

import random

from conftest import fake_providers

from pbs import bandit, timeutil
from pbs.deliver import delivery_due, morning_delivery
from pbs.llm.base import LLMError
from pbs.rank import Candidate, allocate, build_candidates, build_memory


def test_morning_delivery_fills_slots_with_caps(make_ctx):
    ctx = make_ctx()
    res = morning_delivery(ctx)
    assert res["counts"] == {"linkedin": 3, "x": 6}
    cards = ctx.store.select("cards", "delivery_id = ?", (res["id"],))
    for platform in ("linkedin", "x"):
        mine = [c for c in cards if c["platform"] == platform]
        assert sorted(c["rank"] for c in mine) == list(range(1, len(mine) + 1))
        assert sum(1 for c in mine if c["mode"] == "interview") <= 1
        assert len({c["topic_id"] for c in mine}) == len(mine)  # no topic twice on a platform
    x_formats = [c["format"] for c in cards if c["platform"] == "x"]
    assert 2 <= x_formats.count("x_reply") <= 3  # small account: reply angles on the biggest news, capped
    for c in cards:
        assert c["status"] in ("suggested", "needs_input", "blocked")
        if c["status"] == "suggested":
            assert c["draft"] and len(c["hooks"]) == 3 and c["versions"]["prompt"]
            assert c["expires_at"] > timeutil.now_iso()


def test_delivery_is_idempotent_per_local_date(make_ctx):
    ctx = make_ctx()
    assert delivery_due(ctx)
    morning_delivery(ctx)
    assert not delivery_due(ctx)
    assert morning_delivery(ctx, scout=False) is None


def _single_candidates(n):
    return [Candidate(topic={"id": f"t{i}"}, platform="x", pillar=["tech", "startups", "affairs"][i % 3],
                      fmt="x_single", mode="external", base=1.0 - i / 100, parts={"momentum": 0.5})
            for i in range(n)]


def test_reply_slots_are_reserved_only_while_x_account_is_small(make_ctx):
    ctx = make_ctx()
    arms = bandit.compute_arms(ctx.store, ctx.settings)
    small = allocate(ctx, "x", _single_candidates(10), arms, random.Random(1))
    assert [c.fmt for c in small].count("x_reply") == 2
    ctx.store.upsert("account_stats", {"id": "acs_x_2026-09-27", "date": "2026-09-27", "platform": "x",
                                       "followers": 900})
    big = allocate(ctx, "x", _single_candidates(10), arms, random.Random(1))
    assert [c.fmt for c in big].count("x_reply") == 0


def test_quota_exhaustion_degrades_to_brief_cards(make_ctx):
    quota = LLMError("daily quota reached", status=429, quota=True)
    providers = fake_providers()
    for p in providers.values():
        p.fail_with = quota
    ctx = make_ctx(providers=providers)
    res = morning_delivery(ctx)
    cards = ctx.store.select("cards", "delivery_id = ?", (res["id"],))
    assert cards, "a delivery still happens without any model"
    assert ctx.run.degraded in ("fewer_cards", "brief_cards")
    drafted = [c for c in cards if c["draft_state"] == "brief"]
    assert drafted and all(c["draft"] is None and c["angle"] for c in drafted)
    assert all(c["status"] in ("suggested", "needs_input") for c in cards)


def test_fewer_cards_when_budget_is_short(make_ctx):
    ctx = make_ctx()
    ctx.settings.llm.daily_cap = 7  # translate + triage + ~5 drafts
    res = morning_delivery(ctx)
    total = sum(res["counts"].values())
    assert total >= ctx.settings.platforms.linkedin.min_slots + ctx.settings.platforms.x.min_slots
    assert ctx.run.degraded is not None


def test_bandit_observation_semantics(settings):
    engaged = {"d1"}
    base = {"platform": "x", "delivery_id": "d1"}
    val = bandit.observation_value
    assert val({**base, "status": "posted"}, None, settings, engaged, {}) == 1.0
    assert val({**base, "status": "skipped", "skip": {"reason": "off_brand"}}, None, settings, engaged, {}) == 0.0
    assert val({**base, "status": "skipped", "skip": {"reason": "wrong_timing"}}, None, settings, engaged, {}) is None
    assert val({**base, "status": "expired"}, None, settings, engaged, {}) == 0.2
    assert val({**base, "status": "expired", "delivery_id": "d2"}, None, settings, engaged, {}) is None
    blended = val({**base, "status": "posted"}, {"perf": 0.5}, settings, engaged, {"x": True})
    assert abs(blended - (0.6 + 0.4 * 0.5)) < 1e-9


def test_priors_follow_strategy_weights(settings):
    arms = bandit.compute_arms(store=_EmptyStore(), settings=settings)
    receipts = arms["linkedin:receipts:li_text"].prior_mean
    learning = arms["linkedin:learning:li_text"].prior_mean
    assert receipts > learning  # 30% vs 20%
    assert learning >= 0.1 and receipts <= 0.9


def test_posts_move_arm_means(make_ctx):
    ctx = make_ctx()
    now = timeutil.now_iso()
    for i in range(6):
        ctx.store.insert("cards", {"id": f"c{i}", "platform": "x", "pillar": "startups", "format": "x_single",
                                   "arm": "x:startups:x_single", "delivery_id": "d1", "status": "posted",
                                   "created_at": now, "delivered_at": now, "title": "t", "mode": "external"})
    arms = bandit.compute_arms(ctx.store, ctx.settings)
    arm = arms["x:startups:x_single"]
    assert arm.mean > arm.prior_mean and arm.n_obs > 5


def test_allocation_respects_learned_mix(make_ctx):
    ctx = make_ctx()
    from pbs.scout.scouting import run_scouts
    from pbs.topics import build_topics

    run_scouts(ctx)
    build_topics(ctx)
    topics = ctx.store.select("topics")
    cands = build_candidates(ctx, topics, build_memory(ctx), use_llm=False)
    arms = bandit.compute_arms(ctx.store, ctx.settings)
    counts = {"tech": 0}
    for seed in range(20):
        chosen = allocate(ctx, "x", cands["x"], arms, random.Random(seed))
        counts["tech"] += sum(1 for c in chosen if c.pillar == "tech")
    assert counts["tech"] / 20 <= 3.6  # ~35% of 6 slots, never the whole set


class _EmptyStore:
    def select(self, *a, **k):
        return []

    def count(self, *a, **k):
        return 0

    @property
    def conn(self):
        class _C:
            def execute(self, *a, **k):
                return []

        return _C()


def test_candidate_arm_id():
    c = Candidate(topic={"id": "t"}, platform="x", pillar="tech", fmt="x_reply", mode="external", base=1.0)
    assert c.arm == "x:tech:x_reply"

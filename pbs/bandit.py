"""Thompson sampling over pillar × format arms per platform, recomputed from the signal log each run.

Every observation is weighted by 0.5^(age / half-life), so the arm state is a pure function of the
history plus the priors: reproducible, auditable, and immune to drift from partial updates.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from . import timeutil
from .settings import Settings
from .store import Store


@dataclass
class ArmState:
    id: str
    platform: str
    pillar: str
    format: str
    alpha: float
    beta: float
    prior_mean: float
    n_obs: float

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def sample(self, rng: random.Random) -> float:
        return rng.betavariate(max(self.alpha, 1e-3), max(self.beta, 1e-3))

    def as_row(self) -> dict[str, Any]:
        return {"id": self.id, "platform": self.platform, "pillar": self.pillar, "format": self.format,
                "alpha": round(self.alpha, 4), "beta": round(self.beta, 4), "mean": round(self.mean, 4),
                "n_obs": round(self.n_obs, 3), "prior_mean": round(self.prior_mean, 4),
                "updated_at": timeutil.now_iso()}


def arm_id(platform: str, pillar: str, fmt: str) -> str:
    return f"{platform}:{pillar}:{fmt}"


def prior_mean(settings: Settings, platform: str, pillar: str, fmt: str) -> float:
    weights = settings.normalized_weights(platform)
    wmax = max(weights.values()) or 1.0
    m_pillar = 0.25 + 0.5 * (weights.get(pillar, 0.0) / wmax)
    m_format = settings.formats[fmt].prior if fmt in settings.formats else 0.5
    return min(0.9, max(0.1, m_pillar + (m_format - 0.5)))


def feasible_arms(settings: Settings, platform: str) -> list[tuple[str, str]]:
    return [(key, fmt) for key, pillar in settings.pillars(platform).items() for fmt in pillar.formats]


def observation_value(card: dict[str, Any], post: dict[str, Any] | None, settings: Settings,
                      engaged_deliveries: set[str], perf_active: dict[str, bool]) -> float | None:
    """The reward a delivered card contributes to its arm, or None for no observation."""
    status = card.get("status")
    lp = settings.learning
    if status == "posted":
        perf = (post or {}).get("perf")
        if perf is not None and perf_active.get(card["platform"], False):
            return (1 - lp.perf_blend) * 1.0 + lp.perf_blend * float(perf)
        return 1.0
    if status == "skipped":
        reason = (card.get("skip") or {}).get("reason", "other")
        value = lp.skip_values.get(reason, lp.skip_values.get("other", 0.1))
        return None if value is None else float(value)
    if status == "expired":
        if card.get("delivery_id") and card["delivery_id"] in engaged_deliveries:
            return lp.expired_value
        return None
    return None


def compute_arms(store: Store, settings: Settings) -> dict[str, ArmState]:
    lp = settings.learning
    arms: dict[str, ArmState] = {}
    for platform in ("linkedin", "x"):
        for pillar, fmt in feasible_arms(settings, platform):
            m = prior_mean(settings, platform, pillar, fmt)
            s = lp.prior_strength
            arms[arm_id(platform, pillar, fmt)] = ArmState(arm_id(platform, pillar, fmt), platform, pillar, fmt,
                                                           alpha=m * s, beta=(1 - m) * s, prior_mean=m, n_obs=0.0)
    if lp.frozen:
        frozen = {r["id"]: r for r in store.select("bandit_arms")}
        for aid, arm in arms.items():
            row = frozen.get(aid)
            if row:
                arm.alpha, arm.beta, arm.n_obs = float(row["alpha"]), float(row["beta"]), float(row["n_obs"] or 0)
        return arms

    cards = store.select("cards", "delivery_id IS NOT NULL AND arm IS NOT NULL AND status IN "
                         "('posted','skipped','expired')")
    engaged = {r[0] for r in store.conn.execute(
        "SELECT DISTINCT delivery_id FROM cards WHERE delivery_id IS NOT NULL AND status IN "
        "('posted','skipped','editing')")}
    posts = {p["card_id"]: p for p in store.select("posts")}
    perf_active = {platform: store.count("posts", "platform = ? AND perf IS NOT NULL", (platform,))
                   >= lp.metrics_min_posts for platform in ("linkedin", "x")}
    now = timeutil.now()
    for card in cards:
        arm = arms.get(card["arm"])
        if arm is None:
            continue
        value = observation_value(card, posts.get(card["id"]), settings, engaged, perf_active)
        if value is None:
            continue
        when = timeutil.parse(card.get("status_changed_at") or card.get("delivered_at") or card.get("created_at"))
        age_days = max(0.0, (now - when).total_seconds() / 86400) if when else 0.0
        w = 0.5 ** (age_days / lp.half_life_days)
        arm.alpha += w * value
        arm.beta += w * (1.0 - value)
        arm.n_obs += w
    return arms


def snapshot(store: Store, arms: dict[str, ArmState]) -> None:
    store.delete_where("bandit_arms", "1 = 1")
    for arm in arms.values():
        store.upsert("bandit_arms", arm.as_row())

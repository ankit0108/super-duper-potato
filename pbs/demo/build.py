"""`pbs demo`: build the desk's demo data by running the real pipeline over three simulated weeks.

Past days: each morning a scheduled tick delivers that day's cards. The stories come from history.py, but
the cards are created, drafted (by the demo model, through the real prompt, router, guardrails and budget
code) and recorded by the pipeline itself. Ankit's actions go in as desk events: picks, edits, posts,
skips, metrics, follower counts, a stance, a rule, proposal decisions and a request. The same ticks the
desk triggers apply them. Expiry, rewards, the bandit, the voice profile, the Saturday batch and the Monday
reflection run because they're due, exactly as in production.

Today: a real scouting tick against the mock web (web.py) fills the board.

The result is deterministic apart from run durations, and export validates it against the desk contract.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import re
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import deliver, export, ids, log, textutil, tick, timeutil
from ..context import Ctx
from ..contracts import DeskState
from ..llm.fake import FakeProvider
from ..rank import Candidate
from ..settings import load as load_settings
from ..store import Store
from . import history
from .content import demo_handlers
from .web import MockWeb, build_world, rss

TZ = "Australia/Melbourne"
TODAY = dt.date(2026, 9, 28)  # a Monday, before daylight saving starts on 4 October
DAYS = 21
VISIBLE_FROM = DAYS - 8  # the desk shows cards from the last eight days (older ones only if posted)
BLOCKLIST = "Contoso\nFabrikam\nNorthwind Traders"  # fictional: the demo shows the check configured

LI_POST_DAYS = [[1, 1, 0, 1, 1, 1, 0], [1, 1, 1, 1, 1, 1, 0], [1, 1, 1, 1, 1, 1, 1]]
X_POSTS = [[1, 1, 1, 0, 1, 2, 1], [2, 1, 1, 2, 1, 1, 1], [2, 2, 1, 2, 2, 1, 2]]
LI_RANK_WEIGHTS = [[0.45, 0.35, 0.2], [0.55, 0.3, 0.15], [0.65, 0.25, 0.1]]
X_RANK_WEIGHTS = [0.34, 0.2, 0.2, 0.1, 0.11, 0.05]
SKIP_REASONS = [("not_interesting", 0.45), ("wrong_timing", 0.2), ("off_brand", 0.15), ("already_covered", 0.12),
                ("too_risky", 0.08)]
HOOK_PREFERENCE = ["number", "question", "observation", "contrarian", "how-to", "story"]
CLOSERS = ["Where have you seen this play out?", "What would you add?", "Curious where others land on this."]
PINNED = {7: "On this day in 1949", 8: "Engineers' Day"}  # history posts on 14 and 15 September


def request_world(ref: dt.datetime) -> dict[str, tuple[int, str, str]]:
    """Search results for the demo's on-demand request."""

    def at(hours: float) -> dt.datetime:
        return ref - dt.timedelta(hours=hours)

    return {
        "news.google.com/rss/search?q=MCP": (200, "application/rss+xml", rss("Google News", [
            {"title": "Enterprises weigh MCP gateways to control what AI agents can reach - Enterprise Tech Weekly",
             "url": "https://news.google.com/rss/articles/mcp-gateways", "publisher": "Enterprise Tech Weekly",
             "summary": "", "at": at(30)},
            {"title": "Remote MCP servers add OAuth support as adoption grows - Developer News",
             "url": "https://news.google.com/rss/articles/mcp-oauth", "publisher": "Developer News", "summary": "",
             "at": at(52)},
        ])),
        "hn.algolia.com/api/v1/search?query=MCP": (200, "application/json", json.dumps({"hits": [
            {"title": "Show HN: An open-source MCP gateway with per-tool permissions and audit logs",
             "url": "https://example.dev/mcp-gateway", "points": 180, "num_comments": 64,
             "created_at": timeutil.iso(at(20)), "objectID": "41000900"},
        ]})),
    }


@contextmanager
def _demo_environment() -> Iterator[None]:
    keep = {k: os.environ.get(k) for k in ("PBS_BLOCKLIST", "GEMINI_API_KEY", "GITHUB_TOKEN", "PBS_NTFY_TOPIC",
                                           "PBS_TELEGRAM_BOT_TOKEN", "PBS_TELEGRAM_CHAT_ID", "PBS_PUBLIC_LOGS")}
    os.environ.update({"PBS_BLOCKLIST": BLOCKLIST, "GEMINI_API_KEY": "demo", "GITHUB_TOKEN": "demo"})
    for k in ("PBS_NTFY_TOPIC", "PBS_TELEGRAM_BOT_TOKEN", "PBS_TELEGRAM_CHAT_ID"):
        os.environ.pop(k, None)
    os.environ["PBS_PUBLIC_LOGS"] = "1"
    ids.seed(2609)
    try:
        yield
    finally:
        timeutil.freeze(None)
        for k, v in keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def build_demo(out: Path, data_dir: Path | None = None) -> Path:
    """Simulate three weeks plus this morning, then write desk.json for the desk's demo mode."""
    with _demo_environment(), tempfile.TemporaryDirectory(prefix="pbs-demo-") as tmp:
        root = Path(data_dir) if data_dir else Path(tmp) / "data"
        if root.exists() and any(root.iterdir()):
            raise SystemExit(f"{root} is not empty; pass an empty or new directory")
        Simulation(root).run()
        desk = json.loads((root / "desk" / "desk.json").read_text(encoding="utf-8"))
        DeskState.model_validate(desk)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "desk.json"
        path.write_text(json.dumps(desk, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        log.info(f"demo: {len(desk.get('cards', []))} cards, {len(desk.get('posts', []))} posts -> {path}")
        return path


# ---------------------------------------------------------------------------
# The simulation
# ---------------------------------------------------------------------------


@dataclass
class DayPlan:
    li: list[history.Story]
    x: list[tuple[history.Story, str]]  # (story, format) in rank order
    li_post: int | None  # rank posted on LinkedIn
    x_posts: list[int]  # ranks posted on X
    explore: set[tuple[str, int]] = field(default_factory=set)
    experiment: dict[str, tuple[int, dict[str, Any]]] = field(default_factory=dict)


class StoryPool:
    """Fresh stories for cards the desk will show; any story for older cards nobody will see again."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.fresh = {"full": list(history.FULL), "affairs": list(history.AFFAIRS), "startups": list(history.STARTUPS)}
        for key in self.fresh:
            rng.shuffle(self.fresh[key])
        self.used: set[str] = set()
        self.all = {k: list(v) for k, v in self.fresh.items()}

    def take(self, kind: str, fresh: bool, avoid: set[str]) -> history.Story:
        if fresh:
            for i, story in enumerate(self.fresh[kind]):
                if story.title not in avoid:
                    self.used.add(story.title)
                    return self.fresh[kind].pop(i)
            log.warn(f"demo: ran out of fresh {kind} stories; reusing one")
        options = [s for s in self.all[kind] if s.title not in avoid and s.title not in self.used] or \
            [s for s in self.all[kind] if s.title not in avoid]
        return self.rng.choice(options)

    def pinned(self, prefix: str) -> history.Story:
        for i, story in enumerate(self.fresh["affairs"]):
            if story.title.startswith(prefix) or prefix in story.title:
                self.used.add(story.title)
                return self.fresh["affairs"].pop(i)
        raise KeyError(prefix)


class Simulation:
    def __init__(self, root: Path):
        self.root = root
        self.settings, _ = load_settings()
        handlers = demo_handlers()
        self.providers = {name: FakeProvider(name, handlers=handlers) for name in self.settings.llm.providers}
        self.rng = random.Random(28)
        self.pool = StoryPool(random.Random(9))
        self.quiet = MockWeb(world={})
        self.followers = {"linkedin": 3100.0, "x": 12.0}
        self.metrics_due: list[tuple[dt.date, str]] = []  # (due local date, post id)
        self.proposals_seen: set[str] = set()
        self.batch = 0

    # -- time and ticks ---------------------------------------------------------------------------
    @staticmethod
    def at(day: dt.date, hhmm: str) -> dt.datetime:
        return timeutil.at_local_time(day, hhmm, TZ)

    def tick(self, when: dt.datetime, trigger: str, *, hints: set[str] | None = None,
             morning: Callable[[Ctx], dict[str, Any] | None] | None = None, web: MockWeb | None = None) -> dict[str, Any]:
        timeutil.freeze(when)
        return tick.run(self.root, trigger=trigger, hints=hints, transport=(web or self.quiet).transport(),
                        llm_providers=self.providers, sleep=lambda s: None, send_notifications=False, morning=morning)

    def session(self, when: dt.datetime, events: list[dict[str, Any]], web: MockWeb | None = None) -> dict[str, Any]:
        """What the desk does: write one inbox batch, then dispatch a run."""
        folder = self.root / "inbox"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = when.strftime("%Y%m%dT%H%M%S")
        batch = {"v": 1, "id": f"evb_{stamp}_demo", "device": "demo-phone", "created_at": timeutil.iso(when),
                 "events": [{"id": ev.pop("id", None) or f"ev_{stamp}_{i}", **ev} for i, ev in enumerate(events)]}
        (folder / f"{stamp}-demo-phone.json").write_text(json.dumps(batch, ensure_ascii=False), encoding="utf-8")
        return self.tick(when, "workflow_dispatch", web=web)

    def store(self) -> Store:
        return Store.open(self.root)

    # -- the whole run -----------------------------------------------------------------------------
    def run(self) -> None:
        start = TODAY - dt.timedelta(days=DAYS)
        for i in range(DAYS):
            self.day(i, start + dt.timedelta(days=i))
        self.today()
        self.finish()

    def day(self, i: int, day: dt.date) -> None:
        week, weekday = divmod(i, 7)
        plan = self.plan(i, week, weekday)
        late = i == 2  # one slow runner, so the on-time gate has something to show
        morning_at = self.at(day, "06:24" if late else f"05:{41 + (i * 7) % 9:02d}")
        self.tick(morning_at, "schedule", morning=self.morning(i, plan))
        cards = self.delivered(day)
        am, pm = self.actions(i, week, day, plan, cards)
        if i in (1, 4) and plan.li_post:
            self.rewrite_first(day, cards["linkedin"][plan.li_post - 1])
            cards = self.delivered(day)
        am_events = self.post_events(i, week, day, am, cards, "07:05")
        am_events += self.extras(i, day, "am")
        if am_events:
            self.session(self.at(day, f"07:{20 + i % 30:02d}") + dt.timedelta(minutes=45), am_events)
        pm_events = self.post_events(i, week, day, pm, cards, "18:10")
        pm_events += self.metric_events(i, day)
        pm_events += self.follower_events(i, day)
        pm_events += self.extras(i, day, "pm")
        web = None
        if i == DAYS - 1:
            web = MockWeb(world={**build_world(self.at(day, "20:40")), **request_world(self.at(day, "20:40"))},
                          filler=True)
        if pm_events:
            self.session(self.at(day, f"20:{31 + i % 20:02d}"), pm_events, web=web)
        if weekday == 5:
            self.tick(self.at(day, "19:04"), "schedule")  # the Saturday batch is due
        self.organic_growth()

    # -- planning a past day -----------------------------------------------------------------------
    def plan(self, i: int, week: int, weekday: int) -> DayPlan:
        rng = self.rng
        visible = i >= VISIBLE_FROM
        li_post = None
        if LI_POST_DAYS[week][weekday]:
            li_post = rng.choices([1, 2, 3], weights=LI_RANK_WEIGHTS[week])[0]
        experiment_day = 7 <= i < 14
        if experiment_day and li_post and i % 7 in (0, 2, 3, 5):
            li_post = 2  # the experiment card gets picked on four of seven days
        n_x = X_POSTS[week][weekday]
        x_posts: list[int] = []
        pinned = PINNED.get(i)
        if pinned:
            x_posts.append(2)
        x_rank_of_li = {1: 1, 2: 3, 3: 5}
        if li_post and not visible and len(x_posts) < n_x and rng.random() < 0.7:
            x_posts.append(x_rank_of_li[li_post])  # the same story on both platforms
        ranks = range(1, 7) if visible else (2, 4, 6)
        weights = X_RANK_WEIGHTS if visible else [0.5, 0.25, 0.25]
        while len(x_posts) < n_x:
            r = rng.choices(ranks, weights=weights)[0]
            if r not in x_posts:
                x_posts.append(r)

        def fresh_li(rank: int) -> bool:
            return visible or li_post == rank or x_rank_of_li[rank] in x_posts

        taken: set[str] = set()
        li: list[history.Story] = []
        for rank in (1, 2, 3):
            s = self.pool.take("full", fresh_li(rank), taken)
            taken.add(s.title)
            li.append(s)
        a1 = self.pool.pinned(pinned) if pinned else self.pool.take("affairs", visible or 2 in x_posts, taken)
        a2 = self.pool.take("affairs", visible or 6 in x_posts, taken | {a1.title})
        s1 = self.pool.take("startups", visible or 4 in x_posts, taken)
        x = [(li[0], "x_reply"), (a1, "x_thread" if a1.thread else "x_single"),
             (li[1], "x_thread" if li[1].thread else "x_single"), (s1, "x_single"),
             (li[2], "x_quote" if i % 3 == 0 else "x_single"), (a2, "x_single")]
        plan = DayPlan(li=li, x=x, li_post=li_post, x_posts=sorted(x_posts))
        if i % 3 == 1:
            plan.explore.add(("linkedin", 3))
        if i % 4 == 2:
            plan.explore.add(("x", 6))
        return plan

    def morning(self, i: int, plan: DayPlan) -> Callable[[Ctx], dict[str, Any] | None]:
        def run(ctx: Ctx) -> dict[str, Any]:
            now = timeutil.now()
            experiments = {e.get("platform"): e for e in ctx.store.select("experiments", "status = 'active'")}
            out: dict[str, list[Candidate]] = {"linkedin": [], "x": []}
            for rank, story in enumerate(plan.li, 1):
                pillar = story.li_pillar or "industry"
                exp = experiments.get("linkedin") if rank == 2 and 7 <= i < 14 and \
                    (experiments.get("linkedin") or {}).get("pillar") in (None, pillar) else None
                out["linkedin"].append(self.candidate(ctx, i, story, "linkedin", pillar, "li_text", rank, now,
                                                      explore=("linkedin", rank) in plan.explore or exp is not None,
                                                      experiment=exp))
            for rank, (story, fmt) in enumerate(plan.x, 1):
                exp = experiments.get("x") if i >= 14 and story.x_lane == (experiments.get("x") or {}).get("pillar") \
                    and rank == 2 else None
                out["x"].append(self.candidate(ctx, i, story, "x", story.x_lane, fmt, rank, now,
                                               explore=("x", rank) in plan.explore or exp is not None, experiment=exp))
            return deliver.deliver_plan(ctx, out, deliver.delivery_id(ctx.local_date_str()))

        return run

    def candidate(self, ctx: Ctx, i: int, story: history.Story, platform: str, pillar: str, fmt: str, rank: int,
                  now: dt.datetime, *, explore: bool, experiment: dict[str, Any] | None) -> Candidate:
        topic = self.topic(ctx, i, story, now)
        fit = round(0.92 - 0.07 * rank + 0.01 * (i % 3), 3)
        parts = {"fit": fit, "timeliness": round(0.95 - 0.05 * rank, 3), "momentum": round(0.6 - 0.05 * rank, 3),
                 "novelty": 1.0, "angle_potential": 5 - min(rank, 3)}
        base = round(fit * parts["timeliness"] * (0.7 + 0.3 * parts["momentum"]), 4)
        return Candidate(topic=topic, platform=platform, pillar=pillar, fmt=fmt, mode="external", base=base,
                         parts=parts, kind="news", angle=story.angle or None, affairs_type=story.affairs_type,
                         explore=explore, experiment=experiment, score=round(base * (0.8 - 0.04 * rank), 4))

    def topic(self, ctx: Ctx, i: int, story: history.Story, now: dt.datetime) -> dict[str, Any]:
        """The item and topic rows the scouts would have produced for this story."""
        topic_id = ids.stable_id("top", story.title, str(i))
        existing = ctx.store.get("topics", topic_id)
        if existing:
            return existing
        hours = 3 + (int(ids.short_hash(story.title), 16) % 14)
        published = now - dt.timedelta(hours=hours)
        slug = "-".join(textutil.sim_tokens(story.title)[:6]) or "story"
        host = "".join(ch for ch in story.publisher.casefold() if ch.isalnum())
        url = f"https://{host}.example/{published:%Y/%m/%d}/{slug}"
        item_id = ids.stable_id("itm", story.title, str(i))
        ctx.store.upsert("items", {
            "id": item_id, "source_id": "src_demo", "scout": story.scout, "tier": story.tier, "url": url,
            "canonical_url": textutil.canonical_url(url), "title": story.title, "summary": story.fact, "lang": "en",
            "published_at": timeutil.iso(published), "fetched_at": timeutil.iso(now),
            "title_key": textutil.title_key(story.title), "topic_id": topic_id,
            "signals": {"publisher": story.publisher}, "origin": "history",
        })
        if story.affairs_type == "history":
            note = "On this day."
        else:
            note = f"Reported by {story.publisher} {hours} hours ago."
        row = {"id": topic_id, "origin": "history", "scout": story.scout, "tier": story.tier, "title": story.title,
               "summary": story.fact, "item_ids": [item_id], "source_ids": ["src_demo"],
               "publishers": [story.publisher], "n_sources": 1, "first_seen_at": timeutil.iso(now),
               "last_seen_at": timeutil.iso(now), "newest_published_at": timeutil.iso(published),
               "why_now": {"note": note}, "fit": {}, "status": "carded", "updated_at": timeutil.iso(now)}
        ctx.store.upsert("topics", row)
        return row

    def delivered(self, day: dt.date) -> dict[str, list[dict[str, Any]]]:
        rows = self.store().select("cards", "delivery_id = ?", (deliver.delivery_id(day.isoformat()),))
        out: dict[str, list[dict[str, Any]]] = {"linkedin": [], "x": []}
        for c in sorted(rows, key=lambda c: c.get("rank") or 0):
            out[c["platform"]].append(c)
        return out

    # -- Ankit's day ------------------------------------------------------------------------------
    def actions(self, i: int, week: int, day: dt.date, plan: DayPlan,
                cards: dict[str, list[dict[str, Any]]]) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
        """Split the day's posts into the morning and evening sessions."""
        am: list[tuple[str, int]] = []
        pm: list[tuple[str, int]] = []
        if plan.li_post and plan.li_post <= len(cards["linkedin"]):
            am.append(("linkedin", plan.li_post))
        for n, rank in enumerate(plan.x_posts):
            if rank <= len(cards["x"]):
                (am if n == 0 else pm).append(("x", rank))
        return am, pm

    def rewrite_first(self, day: dt.date, card: dict[str, Any]) -> None:
        self.session(self.at(day, "06:52"), [
            {"type": "card.status", "card_id": card["id"], "status": "editing", "at": timeutil.iso(self.at(day, "06:48"))},
            {"type": "card.rewrite", "card_id": card["id"], "chips": ["Shorter"], "note": "",
             "at": timeutil.iso(self.at(day, "06:50"))},
        ])

    def post_events(self, i: int, week: int, day: dt.date, picks: list[tuple[str, int]],
                    cards: dict[str, list[dict[str, Any]]], start: str) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        t = self.at(day, start) + dt.timedelta(minutes=i % 11)
        picked_ids: set[str] = set()
        for platform, rank in picks:
            card = cards[platform][rank - 1]
            picked_ids.add(card["id"])
            if platform == "linkedin":
                secs = self.rng.randint(*[(880, 1300), (480, 780), (240, 470)][week])
                text, hook_index = self.li_final(card, week)
                final = {"text": text}
            else:
                secs = self.rng.randint(*[(230, 420), (140, 260), (60, 150)][week])
                final = self.x_final(card, week)
                hook_index = None
            events.append({"type": "card.status", "card_id": card["id"], "status": "editing", "at": timeutil.iso(t)})
            mid = t + dt.timedelta(seconds=int(secs * 0.6))
            events.append({"type": "card.edit", "card_id": card["id"], "at": timeutil.iso(mid), **final,
                           **({"hook_index": hook_index} if hook_index is not None else {})})
            done = t + dt.timedelta(seconds=secs)
            events.append({"type": "card.posted", "card_id": card["id"], "at": timeutil.iso(done),
                           "posted_at": timeutil.iso(done), "editing_seconds": secs, **final,
                           **({"hook_index": hook_index} if hook_index is not None else {})})
            self.metrics_due.append((day + dt.timedelta(days=2), card["id"]))
            t = done + dt.timedelta(minutes=self.rng.randint(4, 25))
        if start.startswith("07"):
            events += self.skip_events(i, day, cards, picked_ids, t)
        return events

    def skip_events(self, i: int, day: dt.date, cards: dict[str, list[dict[str, Any]]], picked: set[str],
                    t: dt.datetime) -> list[dict[str, Any]]:
        events = []
        plan_posts = {c["id"] for platform in cards.values() for c in platform} & picked
        for platform, count in (("linkedin", 1), ("x", 2 if i % 2 else 1)):
            pool = [c for c in cards[platform] if c["id"] not in plan_posts and c["id"] not in picked
                    and c["status"] in ("suggested", "blocked")]
            self.rng.shuffle(pool)
            for card in pool[:count]:
                if self.rng.random() > 0.72:
                    continue
                reason = self.rng.choices([r for r, _ in SKIP_REASONS], weights=[w for _, w in SKIP_REASONS])[0]
                if card.get("affairs_type") and reason == "off_brand":
                    reason = "wrong_timing"
                events.append({"type": "card.skip", "card_id": card["id"], "reason": reason,
                               "at": timeutil.iso(t + dt.timedelta(minutes=2))})
        return events

    def li_final(self, card: dict[str, Any], week: int) -> tuple[str, int | None]:
        """His LinkedIn edits: the learnable ones (filler, closing summary, hook type) plus personal ones that
        become rarer as the drafts get closer to his voice."""
        paras = [p for p in ((card.get("draft") or {}).get("text") or "").split("\n\n") if p.strip()]
        hooks = card.get("hooks") or []
        hook_index = None
        if hooks and paras:
            best = min(range(len(hooks)), key=lambda k: HOOK_PREFERENCE.index(hooks[k]["type"])
                       if hooks[k]["type"] in HOOK_PREFERENCE else 99)
            if hooks[best]["text"] != paras[0]:
                hook_index = best
                paras[0] = hooks[best]["text"]
        kept = []
        for p in paras:
            if p.startswith("Bottom line:"):
                continue
            for fluff, _ in history.FLUFF:
                p = p.replace(f"{fluff} ", "")
            kept.append(p)
        if len(kept) >= 4 and self.rng.random() < [0.9, 0.7, 0.55][week]:
            sentences = textutil.split_sentences(kept[2])
            if len(sentences) > 1:
                kept[2] = " ".join(sentences[:-1])
        if kept and kept[-1].endswith("?") and self.rng.random() < [0.7, 0.5, 0.35][week]:
            kept[-1] = CLOSERS[self.rng.randrange(len(CLOSERS))]
        return "\n\n".join(kept), hook_index

    def x_final(self, card: dict[str, Any], week: int) -> dict[str, Any]:
        d = card.get("draft") or {}
        if card["format"] == "x_thread":
            posts = [p for p in d.get("posts") or [] if not p.startswith(history.RECAP)]
            if len(posts) >= 4 and self.rng.random() < [0.5, 0.35, 0.2][week]:
                posts.pop(2)
            return {"posts": posts}
        text = d.get("text") or ""
        for tag in history.TAGS.values():
            text = text.replace(f" {tag}", "")
        sentences = textutil.split_sentences(text)
        if len(sentences) >= 2 and self.rng.random() < [0.8, 0.6, 0.4][week]:
            text = " ".join(sentences[:1] + sentences[2:]) if len(sentences) >= 3 else sentences[0]
        return {"text": text}

    def metric_events(self, i: int, day: dt.date) -> list[dict[str, Any]]:
        store = self.store()
        events = []
        due = [(d, cid) for d, cid in self.metrics_due if d <= day]
        self.metrics_due = [(d, cid) for d, cid in self.metrics_due if d > day]
        for _, card_id in due:
            card = store.get("cards", card_id)
            if not card or not card.get("post_id"):
                continue
            post = store.get("posts", card["post_id"])
            if post is None:
                continue
            if post["platform"] == "linkedin" and i >= DAYS - 4:
                self.metrics_due.append((day + dt.timedelta(days=1), card_id))  # comes from the Sunday screenshot
                continue
            values = self.metric_values(post, i)
            self.followers[post["platform"]] += values.get("followers_gained", 0)
            events.append({"type": "post.metrics", "post_id": post["id"], "values": values,
                           "captured_at": timeutil.iso(self.at(day, "20:05")), "at": timeutil.iso(self.at(day, "20:06"))})
        return events

    def metric_values(self, post: dict[str, Any], i: int, later: float = 1.0) -> dict[str, int]:
        rng = self.rng
        hook = (post.get("hook_used") or {}).get("type")
        if post["platform"] == "linkedin":
            base = 1100 * (1.25 if post.get("pillar") == "research" else 1.0) * \
                {"number": 1.2, "question": 1.05}.get(hook or "", 0.9)
            imp = int(base * (1 + 0.025 * i) * rng.lognormvariate(0, 0.3) * later)
            reactions = max(4, int(imp * rng.uniform(0.012, 0.028)))
            return {"impressions": imp, "reactions": reactions, "comments": int(reactions * rng.uniform(0.12, 0.3)),
                    "reposts": int(reactions * rng.uniform(0.02, 0.09)),
                    "followers_gained": max(0, int(imp / rng.uniform(260, 480)))}
        base = 140 * {"tech": 1.0, "affairs": 1.35, "startups": 0.8}.get(post.get("pillar") or "", 1.0) * \
            {"x_thread": 1.5, "x_reply": 0.75}.get(post.get("format") or "", 1.0)
        imp = int(base * (1 + 0.06 * i) * rng.lognormvariate(0, 0.4) * later)
        likes = max(0, int(imp * rng.uniform(0.015, 0.04)))
        return {"impressions": imp, "reactions": likes, "comments": int(likes * rng.uniform(0.1, 0.35)),
                "reposts": int(likes * rng.uniform(0.05, 0.2)), "followers_gained": int(round(imp / rng.uniform(200, 420)))}

    def follower_events(self, i: int, day: dt.date) -> list[dict[str, Any]]:
        if i % 7 not in (2, 6) and i != 0:
            return []
        date, at = day.isoformat(), timeutil.iso(self.at(day, "20:10"))
        return [{"type": "account.stats", "platform": "linkedin", "date": date, "at": at,
                 "followers": int(self.followers["linkedin"]), "profile_views": 120 + 4 * i},
                {"type": "account.stats", "platform": "x", "date": date, "at": at, "followers": int(self.followers["x"])}]

    def organic_growth(self) -> None:
        self.followers["linkedin"] += 1.2
        self.followers["x"] += 0.3

    # -- one-off events ---------------------------------------------------------------------------
    def extras(self, i: int, day: dt.date, when: str) -> list[dict[str, Any]]:
        t = timeutil.iso(self.at(day, "07:02" if when == "am" else "20:20"))
        store = self.store()
        if when == "am" and i == 0:
            return [{"type": "run.request", "tasks": ["doctor"], "at": t}]
        if when == "am" and i == 2:
            return [{"type": "stance.upsert", "stance_id": "ai-regulation", "chosen_key": "risk-based", "at": t}]
        if when == "pm" and i == 6:
            return [{"type": "source.upsert", "source_id": "src_user_oneusefulthing", "name": "One Useful Thing",
                     "kind": "rss", "url": "https://www.oneusefulthing.org/feed", "scout": "tech", "lang": "en",
                     "pillar_hints": ["learning", "industry"], "active": True, "at": t}]
        if when == "pm" and i in (8, 15):
            pending = [p for p in store.select("proposals", "status = 'pending'", order="created_at")
                       if p["id"] not in self.proposals_seen]
            if not pending:
                return []
            self.proposals_seen.add(pending[0]["id"])
            if i == 8:
                return [{"type": "proposal.decide", "proposal_id": pending[0]["id"], "decision": "reject",
                         "note": "Not yet: one more week of data first.", "at": t}]
            return [{"type": "proposal.decide", "proposal_id": pending[0]["id"], "decision": "approve", "at": t}]
        if when == "pm" and i == 11:
            return [{"type": "playbook.rule", "action": "add",
                     "text": "Say 'people', not 'humans', when writing about who reviews or approves work.", "at": t}]
        if when == "pm" and i == 13:
            return [{"type": "settings.update", "patch": {"platforms": {"x": {"thread_max": 5}}}, "at": t}]
        if when == "pm" and i == 17:
            posted = store.select("cards", "status = 'posted'", order="status_changed_at DESC", limit=1)
            if posted:  # a stale tab tries to reopen a posted card: rejected with a reason
                return [{"type": "card.status", "card_id": posted[0]["id"], "status": "editing", "at": t}]
        if when == "pm" and i == DAYS - 1:
            return self.sunday_session(day, t)
        return []

    def sunday_session(self, day: dt.date, t: str) -> list[dict[str, Any]]:
        """The weekly screenshot session, a request for tomorrow, and a doctor check."""
        store = self.store()
        since = timeutil.iso(self.at(day - dt.timedelta(days=7), "00:00"))
        li_posts = store.select("posts", "platform = 'linkedin' AND posted_at >= ?", (since,), order="posted_at")
        entries = []
        for n, post in enumerate(li_posts):
            values = self.metric_values(post, DAYS - 1, later=1.15)
            snippet = textutil.truncate(textutil.opening(post["final_text"]), 90)
            confidence = 0.93
            posted_date = post["posted_at"][:10]
            if n == len(li_posts) - 1:  # a cropped, blurry capture: the match needs a human check
                snippet = "".join(ch for k, ch in enumerate(snippet[:44]) if k % 6 != 5)
                posted_date = (dt.date.fromisoformat(posted_date) + dt.timedelta(days=3)).isoformat()
                confidence = 0.72
            self.followers["linkedin"] += values["followers_gained"] * 0.5
            entries.append({"text_snippet": snippet, "posted_date": posted_date, "confidence": confidence, **values})
        self.metrics_due = [(d, cid) for d, cid in self.metrics_due
                            if (store.get("cards", cid) or {}).get("platform") != "linkedin"]
        shot = {"platform": "linkedin", "kind": "post_analytics", "posts": entries,
                "account": {"followers": int(self.followers["linkedin"]), "profile_views": 214}}
        blob = self.root / "inbox" / "blobs" / "upl_demo_week39" / "linkedin-week.png"
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(json.dumps(shot).encode("utf-8"))  # the demo model 'reads' this as a screenshot
        return [
            {"type": "metrics.upload", "upload_id": "upl_demo_week39", "week": timeutil.iso_week(day),
             "paths": ["inbox/blobs/upl_demo_week39/linkedin-week.png"], "note": "LinkedIn analytics, last 7 days",
             "at": t},
            {"type": "request.create", "request_id": "req_demo_mcp", "query": "MCP servers in production",
             "platforms": {"linkedin": 1, "x": 2}, "notes": "", "at": t},
            {"type": "run.request", "tasks": ["doctor"], "at": t},
        ]

    # -- this morning -----------------------------------------------------------------------------
    def today(self) -> None:
        now = self.at(TODAY, "05:43")
        world = {**build_world(now), **request_world(now)}
        self.tick(now, "schedule", web=MockWeb(world=world, filler=True))
        cards = self.delivered(TODAY)
        x_top = next((c for c in cards["x"] if c["status"] == "suggested" and c["format"] != "x_thread"), None)
        skip = next((c for c in reversed(cards["linkedin"]) if c["status"] == "suggested"), None)
        events: list[dict[str, Any]] = []
        t = self.at(TODAY, "06:22")
        if x_top:
            text = ((x_top.get("draft") or {}).get("text") or "").replace(" #AI #Automation", "")
            events += [{"type": "card.status", "card_id": x_top["id"], "status": "editing", "at": timeutil.iso(t)},
                       {"type": "card.edit", "card_id": x_top["id"], "text": text,
                        "at": timeutil.iso(t + dt.timedelta(minutes=3))}]
        if skip:
            events.append({"type": "card.skip", "card_id": skip["id"], "reason": "already_covered",
                           "at": timeutil.iso(t + dt.timedelta(minutes=5))})
        self.session(self.at(TODAY, "06:31"), events, web=MockWeb(world=world, filler=True))

    def finish(self) -> None:
        """Give runs realistic timings. The simulation's clock is frozen, so every run took zero seconds and
        every model answered in zero milliseconds; the desk would show that as-is."""
        ctx = Ctx.create(self.root, task="export", transport=self.quiet.transport(), llm_providers=self.providers,
                         sleep=lambda s: None)
        rng = random.Random(11)
        base_w = {"setup": 1.2, "inbox": 1, "expire": 0.4, "work": 0.6, "requests": 0.6, "learn": 1.5, "prune": 0.4}
        fetch_w = {"scout": 30.0, "doctor": 16.0, "requests": 6.0}
        model_w = {"morning": 6, "requests": 4, "work": 3, "reflection": 3, "weekly_batch": 3, "metrics": 2,
                   "topics": 1, "doctor": 1}
        runs = ctx.store.select("runs", order="started_at")
        for run in runs:
            steps = run.get("steps") or []
            names = {st["name"] for st in steps}
            calls = int((run.get("llm") or {}).get("calls") or 0)
            base = rng.uniform(8, 15)
            busy = names if "morning" not in names else names - {"requests", "work"}  # a morning run drafts in 'morning'
            fetched = {n: w * rng.uniform(0.8, 1.2) for n, w in fetch_w.items() if n in busy and (n != "requests" or calls)}
            model = calls * rng.uniform(2.4, 3.6)
            model_share = sum(model_w.get(n, 0) for n in busy) or 1
            base_share = sum(base_w.get(n, 0.3) for n in names) or 1

            def secs(name: str, base: float = base, fetched: dict[str, float] = fetched, model: float = model,
                     model_share: float = model_share, base_share: float = base_share, busy: set[str] = busy) -> float:
                return round(base * base_w.get(name, 0.3) / base_share + fetched.get(name, 0.0)
                             + (model * model_w.get(name, 0) / model_share if name in busy else 0.0), 1)

            run["steps"] = [{**st, "secs": secs(st["name"])} for st in steps]
            total = sum(st["secs"] for st in run["steps"])
            run["ended_at"] = timeutil.iso(timeutil.parse(run["started_at"]) + dt.timedelta(seconds=round(total)))
            ctx.store.upsert("runs", run)
        for report in ctx.store.select("doctor_reports"):
            checks = [{**c, "detail": re.sub(r"answered in \d+ ms", lambda _: f"answered in {rng.randint(420, 1900)} ms",
                                             c.get("detail") or "")} for c in report.get("checks") or []]
            ctx.store.update("doctor_reports", report["id"], checks=checks)
        if runs:
            ctx.run.id = runs[-1]["id"]
        export.write(ctx)
        ctx.store.save()

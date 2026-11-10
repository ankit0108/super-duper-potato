"""The platform scouts: one for LinkedIn, one for X.

Each morning a scout
1. plans a few searches for what people on its platform are saying in his field (a cheap model call; run through
   pbs/scout/websearch.py when the TAVILY_API_KEY secret is set), and the results join the day's stories;
2. reads the day's best candidates with the evidence code could gather for each (observed counts, public posts
   found, outlets), scores them on six measures of how far they could travel on its platform, and writes a report:
   opportunities, what it passed on, and why.

The report moves candidates up or down inside the ranking (the lane weights and the learner still set the mix)
and is shown on the desk's Scouts page. Evidence rules are the pipeline's: observed activity, indexed coverage and
the scout's own read are kept apart; a traction mark can't exceed what the evidence supports; the "why" is a
hypothesis. When no model answers, or the day's drafts need the budget, the report is built from the ranking alone.

The scouts' knowledge of their platform is in pbs/prompts/scout_linkedin.md and scout_x.md.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, field_validator

from .. import feedback, log, prompting, textutil, timeutil
from ..context import Ctx
from ..llm.base import AllProvidersFailed, BudgetExhausted, LLMError, LLMRequest
from ..scout import websearch
from ..scout.scouting import DedupIndex, ingest_items, trending_terms

if TYPE_CHECKING:
    from ..rank import Candidate

PLATFORM_LABEL = {"linkedin": "LinkedIn", "x": "X"}
MEASURES = {"linkedin": ("timing", "traction", "stakes", "conversation", "keep", "standing"),
            "x": ("live", "traction", "hook", "edge", "quotable", "standing")}
SOURCE_ID = {"linkedin": "scout-linkedin", "x": "scout-x"}
# Links to a post itself (not a profile, a search page or a company page).
POST_URL = {"linkedin": re.compile(r"^https://([a-z]+\.)?linkedin\.com/(posts|feed/update|pulse)/"),
            "x": re.compile(r"^https://(www\.|mobile\.)?(x|twitter)\.com/[^/]+/status/\d+")}
_SOCIAL_HOST = re.compile(r"^https://([a-z]+\.)?(linkedin|x|twitter)\.com/")
# What a traction mark may be at most, by the evidence behind it.
TRACTION_CAP = {"observed": 3, "indexed": 2, "hypothesis": 1}
RISKS = ("saturated", "late", "thin evidence", "sensitive")
WINDOWS = ("today", "this_week", "evergreen")
X_FORMATS = ("x_reply", "x_quote", "x_single", "x_thread")
PROBE_NOTES = {
    "linkedin": "On LinkedIn, look for practitioners' posts: lessons from real work, reactions to the week's news, "
                "frameworks, numbers from surveys and reports, and disagreements worth joining.",
    "x": "On X, look for what is live now: launches, demos, benchmarks, strong opinions from people in the field, "
         "and posts from larger accounts that are drawing replies.",
}


def report_id(platform: str, local_date: str) -> str:
    return f"sr_{platform}_{local_date}"


def enabled(ctx: Ctx) -> bool:
    return ctx.settings.agents.enabled


def affordable(ctx: Ctx, drafts: int) -> bool:
    """Whether the model budget covers the day's drafts with room for the agents: drafts come first."""
    return ctx.llm.remaining("draft") >= drafts + ctx.settings.agents.reserve


# ---------------------------------------------------------------------------
# Searches
# ---------------------------------------------------------------------------


class _Probe(BaseModel):
    model_config = ConfigDict(extra="ignore")
    q: str
    where: str = "web"
    days: int = 3

    @field_validator("q", mode="before")
    @classmethod
    def _plain(cls, v: Any) -> str:
        # Plain words only: operators and site: prefixes are the search client's business.
        return textutil.normalize_ws(re.sub(r'site:\S+|["()]|\b(OR|AND)\b', " ", str(v or "")))[:120]


class _Probes(BaseModel):
    model_config = ConfigDict(extra="ignore")
    probes: list[_Probe] = []


def _subjects(ctx: Ctx, platform: str) -> list[str]:
    return [f"{p.label}: {textutil.truncate(p.description.strip(), 110)}"
            for p in ctx.settings.pillars(platform).values() if p.weight > 0 and p.mode == "external"]


def _top_stories(ctx: Ctx, limit: int = 8) -> list[str]:
    """The day's most discussed fresh items, by the counts their sources report."""
    since = timeutil.iso(timeutil.now() - dt.timedelta(hours=36))
    scored = []
    for it in ctx.store.select("items", "fetched_at >= ?", (since,)):
        sig = it.get("signals") or {}
        heat = (sig.get("hn_points") or 0) + (sig.get("reddit_score") or 0) / 4 + (sig.get("bsky_likes") or 0) \
            + 40 * len(sig.get("also_seen_in") or [])
        if heat > 0:
            scored.append((heat, it.get("title_en") or it["title"]))
    scored.sort(key=lambda t: -t[0])
    out: list[str] = []
    for _, title in scored:
        if not any(textutil.title_key(title) == textutil.title_key(o) for o in out):
            out.append(textutil.truncate(title, 110))
        if len(out) >= limit:
            break
    return out


def plan_probes(ctx: Ctx, platform: str) -> list[dict[str, Any]]:
    """The scout's searches for today: planned by a model from the day's stories and his subjects, or his standing
    searches when no model can."""
    n = ctx.settings.agents.probes
    if n <= 0:
        return []
    standing = [{"q": q, "where": platform, "days": 3} for q in ctx.settings.agents.standing_probes.get(platform, [])]
    prompt = prompting.render(
        "scout_probes", display_name=ctx.settings.display_name, platform=platform,
        platform_label=PLATFORM_LABEL[platform], platform_notes=PROBE_NOTES[platform], n=n,
        today=ctx.local_date_str(), subjects="; ".join(_subjects(ctx, platform)) or "(none set)",
        stories="; ".join(_top_stories(ctx)) or "(none yet)",
        trending=", ".join(str(t.get("term")) for t in trending_terms(ctx.store)[:12]) or "(none)")
    try:
        out, _ = ctx.llm.call_json(LLMRequest(task="scout_probes", system="You plan web searches. JSON only.",
                                              prompt=prompt, max_output_tokens=500,
                                              prompt_version=prompting.version("scout_probes")), _Probes)
        probes = [{"q": p.q, "where": p.where if p.where in (platform, "web") else platform,
                   "days": p.days if p.days in (1, 3, 7) else 3} for p in out.probes if len(p.q) >= 3]
    except (BudgetExhausted, AllProvidersFailed, LLMError, ValueError) as exc:
        log.info(f"scout: {platform} searches planned without a model ({type(exc).__name__})")
        probes = []
    seen: set[str] = set()
    unique = []
    for p in [*probes, *standing]:
        key = textutil.title_key(p["q"])
        if key and key not in seen:
            seen.add(key)
            unique.append(p)
    return unique[:n]


def run_probes(ctx: Ctx, platform: str) -> list[dict[str, Any]]:
    """Plan and run the scout's searches; what they find joins the day's items, marked as search-cited (a search
    engine returned the page: nothing is known about how it performed). Returns [{query, where, found}]."""
    if not enabled(ctx) or not websearch.available() or websearch.remaining(ctx) <= 0:
        return []
    source = ctx.store.get("sources", SOURCE_ID[platform])
    if source is not None and not source.get("active"):
        return []  # he paused the scout's searches on the Sources page
    source = source or {"id": SOURCE_ID[platform], "scout": "buzz"}
    index = DedupIndex(ctx.store, ctx.settings.scouting.dedup_window_days)
    now = timeutil.now_iso()
    done: list[dict[str, Any]] = []
    kept = 0
    for probe in plan_probes(ctx, platform):
        try:
            rows = websearch.search(ctx, probe["q"], where=probe["where"], days=probe["days"])
        except websearch.SearchUnavailable as exc:
            log.info(f"scout: {platform} search stopped ({exc})")
            break
        raws = []
        for r in rows:
            on = next((p for p, rx in POST_URL.items() if rx.match(r["url"])), None)
            if on is None and (probe["where"] != "web" or _SOCIAL_HOST.match(r["url"])):
                continue  # a profile, company or search page, not a post
            if probe["where"] != "web" and on != probe["where"]:
                continue
            raws.append({
                "url": r["url"], "title": textutil.truncate(r["title"], 180),
                "summary": textutil.truncate(r["content"], 1200),
                "published_at": timeutil.iso(timeutil.parse(r["published"])) if timeutil.parse(r["published"]) else now,
                "lang": "en",
                "publisher": f"{PLATFORM_LABEL[on]} (public post)" if on else textutil.url_host(r["url"]),
                "signals": {"search_cited": 1, "probe": probe["q"], **({"discovery_platform": on} if on else {}),
                            **({"discussion_url": r["url"]} if on else {})},
            })
        new_ids, _ = ingest_items(ctx.store, source, raws, index)
        kept += len(new_ids)
        done.append({"query": probe["q"], "where": probe["where"], "found": len(raws)})
    if done:
        websearch.log_use(ctx, len(done), kept)
        if source.get("kind"):
            ctx.store.update("sources", source["id"], last_fetch_at=now, last_success_at=now, items_last_run=kept,
                             consecutive_failures=0, last_error=None,
                             items_total=int(source.get("items_total") or 0) + kept)
    return done


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def evidence_for(ctx: Ctx, topic: dict[str, Any], platform: str) -> dict[str, Any]:
    """What is known about how a story is travelling: {level, lines, seen_on, x_post, url}. "observed": a public
    endpoint returned counts; "indexed": it was found on a platform or in several outlets, reach unknown;
    "hypothesis": nothing but the story itself."""
    sig = dict((topic.get("why_now") or {}).get("signals") or {})
    items = ctx.store.select("items", "topic_id = ?", (topic["id"],)) if topic.get("id") else []
    seen: dict[str, int] = {}
    x_post = None
    probes: list[str] = []
    for it in items:
        isig = it.get("signals") or {}
        on = isig.get("discovery_platform")
        if on in ("linkedin", "x", "bluesky"):
            seen[on] = seen.get(on, 0) + 1
        if POST_URL["x"].match(it.get("url") or "") and x_post is None:
            x_post = it["url"]
        if isig.get("probe") and isig["probe"] not in probes:
            probes.append(str(isig["probe"]))
    observed: list[str] = []
    if sig.get("hn_points"):
        observed.append(f"{int(sig['hn_points'])} points and {int(sig.get('hn_comments') or 0)} comments on Hacker News")
    if sig.get("reddit_score"):
        observed.append(f"{int(sig['reddit_score']):,} upvotes and {int(sig.get('reddit_comments') or 0):,} comments "
                        "on Reddit")
    bsky = sum(int(sig.get(k) or 0) for k in ("bsky_likes", "bsky_reposts", "bsky_replies"))
    if bsky:
        observed.append(f"{int(sig.get('bsky_likes') or 0)} likes, {int(sig.get('bsky_reposts') or 0)} reposts and "
                        f"{int(sig.get('bsky_replies') or 0)} replies on Bluesky")
    if sig.get("mastodon_accounts"):
        observed.append(f"shared by {int(sig['mastodon_accounts'])} accounts on Mastodon")
    if sig.get("hf_upvotes"):
        observed.append(f"{int(sig['hf_upvotes'])} upvotes on Hugging Face")
    if sig.get("hf_model_rank"):
        observed.append(f"number {int(sig['hf_model_rank'])} on Hugging Face's trending models, "
                        f"{int(sig.get('hf_model_likes') or 0):,} likes")
    indexed: list[str] = []
    outlets = int(topic.get("n_sources") or 1)
    if outlets >= 3:
        indexed.append(f"covered by {outlets} outlets")
    for on in ("linkedin", "x"):
        if seen.get(on):
            indexed.append(f"found in {seen[on]} public {PLATFORM_LABEL[on]} post{'s' if seen[on] != 1 else ''}")
    if sig.get("trend_term"):
        indexed.append(f"“{sig['trend_term']}” is a trending term")
    if probes:
        indexed.append(f"found by today's search for “{probes[0]}”")
    level = "observed" if observed else "indexed" if indexed else "hypothesis"
    url = next((it.get("url") for it in items if it.get("url")), None)
    return {"level": level, "lines": (observed + indexed)[:5], "seen_on": seen,
            "x_post": x_post if platform == "x" else None, "url": url}


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


class _Opp(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    marks: dict[str, Any] = {}
    why: str = ""
    opening: str = ""
    angle: str = ""
    format: str | None = None
    reply_to: str | None = None
    visual: str | None = None
    risk: str | None = None
    window: str | None = None


class _Pass(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    reason: str = ""


class _Report(BaseModel):
    model_config = ConfigDict(extra="ignore")
    note: str = ""
    opportunities: list[_Opp] = []
    passed: list[_Pass] = []


def _mark(value: Any) -> int:
    try:
        return max(0, min(3, int(round(float(value)))))
    except (TypeError, ValueError):
        return 0


def _eligible(cands: list[Candidate]) -> list[Candidate]:
    """What a scout judges: stories from outside written as a post of his own view. Not his interview questions,
    and not funny takes, quotes, excerpts or thoughts: those lanes have their own craft, and a scout's angle or
    format would undo it."""
    return [c for c in cands if c.mode == "external" and c.topic.get("id") and c.post_type is None
            and not str(c.topic["id"]).startswith(("pool:", "bank:")) and c.kind in ("news", "evergreen")
            and not ((c.topic.get("why_now") or {}).get("signals") or {}).get("quote")]


def _his_results(ctx: Ctx, platform: str) -> str:
    """What has earned engagement for him, from his own numbers (never anyone else's)."""
    posts = [p for p in ctx.store.select("posts", "platform = ? AND perf IS NOT NULL", (platform,),
                                         order="perf DESC", limit=3)]
    if not posts:
        return "(no analytics yet)"
    return "; ".join(f"“{textutil.truncate(textutil.opening(p.get('final_text') or ''), 80)}”"
                     f" ({(p.get('hook_used') or {}).get('type') or 'post'})" for p in posts)


def _audience(ctx: Ctx, platform: str) -> str:
    from ..metrics import AUDIENCE_KEY

    rows = ((ctx.store.get_setting(AUDIENCE_KEY, {}) or {}).get(platform) or {}).get("rows") or []
    titles = [f"{r.get('value')} ({r.get('share'):g}%)" for r in rows
              if r.get("category") == "Job title" and isinstance(r.get("share"), (int, float))][:4]
    if titles:
        return "by job title, " + ", ".join(titles) + "; mostly in large companies"
    return "software, AI and data engineers, and people in automation and enterprise IT"


def _recent_posts(ctx: Ctx, platform: str) -> str:
    since = timeutil.iso(timeutil.now() - dt.timedelta(days=7))
    rows = ctx.store.select("posts", "platform = ? AND posted_at >= ?", (platform, since), order="posted_at DESC",
                            limit=8)
    return "; ".join(textutil.truncate(textutil.opening(p.get("final_text") or ""), 70) for p in rows) or "(none)"


def _payload(ctx: Ctx, platform: str, picked: list[Candidate], evidence: dict[str, dict[str, Any]]) -> list[dict]:
    now = timeutil.now()
    out = []
    for i, c in enumerate(picked, 1):
        t = c.topic
        ev = evidence[t["id"]]
        first = timeutil.parse(t.get("first_seen_at") or t.get("last_seen_at"))
        spec = ctx.settings.pillar(platform, c.pillar)
        row: dict[str, Any] = {
            "id": f"C{i}", "title": t.get("title_en") or t.get("title"),
            "summary": textutil.truncate(t.get("summary"), 220), "lane": spec.label if spec else c.pillar,
            "age_hours": round((now - first).total_seconds() / 3600) if first else None,
            "outlets": int(t.get("n_sources") or 1), "publishers": (t.get("publishers") or [])[:3],
            "story": c.story, "evidence": ev["lines"], "evidence_level": ev["level"],
        }
        if platform == "x" and ev["x_post"]:
            row["x_post"] = ev["x_post"]
        if c.angle:
            row["first_angle"] = textutil.truncate(c.angle, 140)
        out.append({k: v for k, v in row.items() if v not in (None, [], "")})
    return out


def _fallback(picked: list[Candidate], evidence: dict[str, dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """A report from the ranking alone: the evidence, no read of why."""
    rows = []
    for c in sorted(picked, key=lambda c: -c.base)[:n]:
        ev = evidence[c.topic["id"]]
        rows.append({"cand": c, "marks": {}, "score": 0.0, "why": "", "opening": "", "angle": c.angle or "",
                     "format": c.fmt, "reply_to": None, "visual": None, "risk": None, "window": None, "ev": ev})
    return rows


def _stored(ctx: Ctx, platform: str, row: dict[str, Any], rank: int) -> dict[str, Any]:
    c: Candidate = row["cand"]
    ev = row["ev"]
    return {
        "id": c.topic["id"], "title": c.topic.get("title_en") or c.topic.get("title") or "", "lane": c.pillar,
        "format": row["format"] or c.fmt, "angle": row["angle"], "url": ev["url"], "card_id": None,
        "score": row["score"], "marks": row["marks"], "evidence_level": ev["level"], "evidence": ev["lines"],
        "why": row["why"], "opening": row["opening"], "risk": row["risk"], "window": row["window"],
        "reply_to": row["reply_to"], "visual": row["visual"], "rank": rank,
    }


def note_of(opp: dict[str, Any]) -> dict[str, Any]:
    """The part of an opportunity kept on its card."""
    return {k: opp.get(k) for k in ("score", "marks", "evidence_level", "evidence", "why", "opening", "risk", "window",
                                    "reply_to", "visual", "rank")}


def _apply(ctx: Ctx, platform: str, cands: list[Candidate], report: dict[str, Any]) -> None:
    """Move candidates by the scout's report: its picks up by their score, what it passed on down. A scout only
    reorders stories inside the ranking; lanes, weights and the learner still decide the mix."""
    opps = {o["id"]: o for o in report.get("opportunities") or []}
    passed = {p["id"] for p in report.get("passed") or []}
    scored = report.get("status") == "ok"
    for c in cands:
        tid = c.topic.get("id")
        opp = opps.get(tid)
        if opp is not None:
            c.scout = note_of(opp)
            if not scored:
                continue
            c.base = round(c.base * (0.7 + 0.6 * float(opp.get("score") or 0)), 4)
            c.parts = {**c.parts, "scout": float(opp.get("score") or 0)}
            if opp.get("angle"):
                c.angle = opp["angle"]
            if platform == "linkedin" and opp.get("visual") and not c.format_note:
                c.format_note = f"The scout suggests a {opp['visual']}: the idea has steps or a comparison."
            spec = ctx.settings.pillar(platform, c.pillar)
            if platform == "x" and spec and opp.get("format") in spec.formats and c.post_type is None \
                    and c.affairs_type != "story" and not c.sensitive:
                c.fmt = opp["format"]
        elif scored and tid in passed:
            c.base = round(c.base * 0.6, 4)
            c.parts = {**c.parts, "scout": 0.0}


def report(ctx: Ctx, platform: str, cands: list[Candidate], probes: list[dict[str, Any]] | None = None,
           *, use_llm: bool = True) -> dict[str, Any]:
    """Write the scout's report for a platform, apply it to the candidates and keep it. A report written in the
    last few hours is used again (a fresh set asks nothing new)."""
    today = ctx.local_date_str()
    rid = report_id(platform, today)
    old = ctx.store.get("scout_reports", rid)
    hours = ctx.settings.ranking.triage_reuse_hours
    since = timeutil.iso(timeutil.now() - dt.timedelta(hours=hours))
    if old and old.get("status") == "ok" and hours > 0 and (old.get("created_at") or "") >= since:
        _apply(ctx, platform, cands, old)
        return old
    agents = ctx.settings.agents
    picked = sorted(_eligible(cands), key=lambda c: -c.base)[:agents.candidates]
    evidence = {c.topic["id"]: evidence_for(ctx, c.topic, platform) for c in picked}
    base: dict[str, Any] = {"id": rid, "platform": platform, "local_date": today, "created_at": timeutil.now_iso(),
                            "searched": bool(probes), "probes": probes or (old or {}).get("probes") or [],
                            "model": None, "provider": None, "note": "", "passed": [], "error": None}
    if not picked:
        row = {**base, "status": "skipped", "opportunities": [], "note": "No outside stories to judge today."}
        ctx.store.upsert("scout_reports", row)
        return row
    rows: list[dict[str, Any]] = []
    status, error = "fallback", None
    if use_llm:
        ref = {f"C{i}": c for i, c in enumerate(picked, 1)}
        from ..rank import x_followers

        prompt = prompting.render(
            f"scout_{platform}", display_name=ctx.settings.display_name, today=today,
            audience=_audience(ctx, platform), results=_his_results(ctx, platform),
            recent_posts=_recent_posts(ctx, platform),
            feedback=feedback.render(feedback.recent_feedback(ctx, limit=6, notes_first=True)),
            followers=x_followers(ctx) if x_followers(ctx) is not None else "few",
            n=agents.opportunities, input_json=_payload(ctx, platform, picked, evidence))
        try:
            out, resp = ctx.llm.call_json(LLMRequest(
                task="scout", system=f"You are an expert {PLATFORM_LABEL[platform]} content scout. You judge only "
                                     "from the evidence you are given and never invent a number.",
                prompt=prompt, max_output_tokens=2600, prompt_version=prompting.version(f"scout_{platform}")),
                _Report)
            used: set[str] = set()
            for o in out.opportunities:
                c = ref.get(o.id.strip().upper())
                if c is None or c.topic["id"] in used:
                    continue  # an id it made up, or the same story twice
                used.add(c.topic["id"])
                ev = evidence[c.topic["id"]]
                marks = {m: _mark(o.marks.get(m)) for m in MEASURES[platform]}
                marks["traction"] = min(marks["traction"], TRACTION_CAP[ev["level"]])
                fmt = o.format if o.format in X_FORMATS and platform == "x" else None
                if fmt == "x_quote" and not ev["x_post"]:
                    fmt = "x_reply"  # nothing to quote: a reply names who to look for instead
                rows.append({
                    "cand": c, "marks": marks, "score": round(sum(marks.values()) / (3 * len(marks)), 3),
                    "why": textutil.truncate(textutil.normalize_ws(o.why), 400),
                    "opening": textutil.truncate(textutil.normalize_ws(o.opening), 240),
                    "angle": textutil.truncate(textutil.normalize_ws(o.angle), 300), "format": fmt,
                    "reply_to": textutil.truncate(textutil.normalize_ws(o.reply_to or ""), 200) or None
                    if fmt in ("x_reply", "x_quote") else None,
                    "visual": o.visual if o.visual in ("carousel", "diagram") and platform == "linkedin" else None,
                    "risk": o.risk if o.risk in RISKS else None,
                    "window": o.window if o.window in WINDOWS else None, "ev": ev})
            rows.sort(key=lambda r: -r["score"])
            rows = rows[:agents.opportunities]
            if rows:
                status = "ok"
                base.update(model=resp.model, provider=resp.provider, note=textutil.truncate(out.note, 300),
                            passed=[{"id": ref[p.id.strip().upper()].topic["id"],
                                     "title": ref[p.id.strip().upper()].topic.get("title_en")
                                     or ref[p.id.strip().upper()].topic.get("title") or "",
                                     "reason": textutil.truncate(textutil.normalize_ws(p.reason), 200)}
                                    for p in out.passed if p.id.strip().upper() in ref
                                    and ref[p.id.strip().upper()].topic["id"] not in used][:10])
            else:
                error = "The scout's reply named no story from today's list"
        except BudgetExhausted:
            error = "Model quota was short, so this report is the ranking with its evidence"
        except (AllProvidersFailed, LLMError, ValueError) as exc:
            error = "No model could write the report, so this is the ranking with its evidence"
            log.info(f"scout: {platform} report without a model ({type(exc).__name__})")
    else:
        error = "The day's drafts needed the model budget, so this report is the ranking with its evidence"
    if status != "ok":
        rows = _fallback(picked, evidence, agents.opportunities)
    row = {**base, "status": status, "error": error,
           "opportunities": [_stored(ctx, platform, r, i) for i, r in enumerate(rows, 1)]}
    ctx.store.upsert("scout_reports", row)
    _apply(ctx, platform, cands, row)
    log.info(f"scout: {platform} report {status}: {len(rows)} opportunities from {len(picked)} candidates, "
             f"{len(row['probes'])} searches")
    return row


def candidate_for(ctx: Ctx, platform: str, opp: dict[str, Any], topic: dict[str, Any]) -> Candidate | None:
    """A candidate from a stored opportunity, for "Draft this" on the Scouts page. None when its lane is gone."""
    from .. import guardrails, posttypes
    from ..rank import Candidate

    spec = ctx.settings.pillar(platform, opp.get("lane") or "")
    if spec is None or not spec.formats or spec.mode != "external":
        return None
    signals = (topic.get("why_now") or {}).get("signals") or {}
    sensitive, reason = guardrails.sensitive_check(topic.get("title_en") or topic.get("title"), topic.get("summary"))
    fmt = opp["format"] if opp.get("format") in spec.formats else spec.formats[0]
    if (sensitive or signals.get("evergreen") or signals.get("otd_year")) and fmt in ("x_reply", "x_quote"):
        fmt = "x_single" if "x_single" in spec.formats else spec.formats[0]
    score = float(opp.get("score") or 0)
    return Candidate(
        topic=topic, platform=platform, pillar=opp["lane"], fmt=fmt, mode="external", base=score,
        parts={"scout": score}, kind="evergreen" if signals.get("evergreen") else "news",
        angle=opp.get("angle") or None, affairs_type="tracker" if opp["lane"] == "affairs" else None,
        post_type=posttypes.for_news(spec.post_types, None), sensitive=sensitive,
        sensitive_reason=reason if sensitive else None, scout=note_of(opp))


def link_cards(ctx: Ctx, card_ids: list[str]) -> None:
    """Note on each report which opportunities became cards."""
    by_report: dict[str, dict[str, str]] = {}
    for cid in card_ids:
        card = ctx.store.get("cards", cid)
        if card and card.get("topic_id") and card.get("scout"):
            by_report.setdefault(report_id(card["platform"], ctx.local_date_str()), {})[card["topic_id"]] = cid
    for rid, linked in by_report.items():
        row = ctx.store.get("scout_reports", rid)
        if not row:
            continue
        opps = [{**o, "card_id": linked.get(o["id"], o.get("card_id"))} for o in row.get("opportunities") or []]
        ctx.store.update("scout_reports", rid, opportunities=opps)


def recent(ctx: Ctx, days: int = 3) -> list[dict[str, Any]]:
    since = (ctx.local_date() - dt.timedelta(days=days)).isoformat()
    return ctx.store.select("scout_reports", "local_date >= ?", (since,), order="local_date DESC, platform")

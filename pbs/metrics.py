"""Analytics screenshots → numbers matched to posts (FR-20). Low-confidence matches wait for review."""

from __future__ import annotations

import difflib
import shutil
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import ids, log, prompting, textutil, timeutil
from .context import Ctx
from .llm.base import BudgetExhausted, LLMRequest, why_unavailable

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
FIELDS = ("impressions", "reactions", "comments", "reposts", "sends", "followers_gained", "profile_views", "link_clicks")


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().lower().replace(",", "")
    mult = 1
    if s.endswith("k"):
        mult, s = 1000, s[:-1]
    elif s.endswith("m"):
        mult, s = 1_000_000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return None


class _PostMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text_snippet: str = ""
    posted_date: str | None = None
    impressions: int | None = None
    reactions: int | None = None
    comments: int | None = None
    reposts: int | None = None
    sends: int | None = None
    followers_gained: int | None = None
    profile_views: int | None = None
    link_clicks: int | None = None
    confidence: float = 0.7

    @field_validator(*FIELDS, mode="before")
    @classmethod
    def _num(cls, v: Any) -> int | None:
        return _to_int(v)


class _Account(BaseModel):
    model_config = ConfigDict(extra="ignore")
    followers: int | None = None
    profile_views: int | None = None

    @field_validator("followers", "profile_views", mode="before")
    @classmethod
    def _num(cls, v: Any) -> int | None:
        return _to_int(v)


class _VisionOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    platform: str | None = None
    kind: str | None = None
    posts: list[_PostMetrics] = Field(default_factory=list)
    account: _Account | None = None


def match_post(ctx: Ctx, platform: str | None, snippet: str, date: str | None) -> tuple[str | None, float]:
    """Best matching post by opening text, platform and date proximity."""
    rows = ctx.store.select("posts", "platform = ?" if platform in ("linkedin", "x") else "1 = 1",
                            (platform,) if platform in ("linkedin", "x") else (), order="posted_at DESC", limit=60)
    snip = textutil.normalize_ws(snippet).casefold()[:160]
    best: tuple[str | None, float] = (None, 0.0)
    second = 0.0
    target = timeutil.parse(date) if date else None
    for post in rows:
        text = textutil.normalize_ws(post["final_text"]).casefold()
        if not snip:
            sim = 0.0
        else:
            window = text[: max(len(snip) + 40, 80)]
            sim = difflib.SequenceMatcher(a=snip, b=window, autojunk=False).ratio()
            if snip in text:
                sim = max(sim, 0.95)
        if target is not None:
            gap = abs((timeutil.parse(post["posted_at"]) - target).total_seconds()) / 86400  # type: ignore[operator]
            sim *= 1.0 if gap <= 2 else 0.85
        if sim > best[1]:
            second = best[1]
            best = (post["id"], sim)
        elif sim > second:
            second = sim
    confidence = best[1] if best[1] - second >= 0.1 else best[1] * 0.8
    return best[0], round(confidence, 3)


def process_uploads(ctx: Ctx) -> dict[str, int]:
    stats = {"uploads": 0, "metrics": 0, "needs_review": 0, "failed": 0}
    for upload in ctx.store.select("metric_uploads", "status = 'pending'", order="created_at"):
        stats["uploads"] += 1
        results: list[dict[str, Any]] = []
        error = None
        for rel in upload.get("paths") or []:
            path = ctx.data_root / rel
            if not path.is_file():
                error = f"missing file {rel}"
                continue
            try:
                res = _extract(ctx, path.read_bytes(), MIME.get(path.suffix.lower(), "image/jpeg"), upload)
                results.append({"path": rel, **res})
                stats["metrics"] += res["metrics"]
                stats["needs_review"] += res["needs_review"]
            except BudgetExhausted as exc:
                error = f"Waiting: {why_unavailable(exc)}; will retry on the next run"
                break
            except Exception as exc:  # noqa: BLE001
                log.error(f"metrics:{upload['id']}", exc)
                results.append({"path": rel, "error": type(exc).__name__})
                stats["failed"] += 1
        if error and error.startswith("Waiting"):
            ctx.store.update("metric_uploads", upload["id"], error=error)
            break
        week = upload.get("week") or timeutil.iso_week(ctx.local_date())
        for rel in upload.get("paths") or []:
            src = ctx.data_root / rel
            if src.is_file():
                dest = ctx.data_root / "media" / "metrics" / week / src.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
        ctx.store.update("metric_uploads", upload["id"], status="processed" if results else "failed",
                         processed_at=timeutil.now_iso(), results={"files": results}, error=error)
    if stats["uploads"]:
        log.info(f"metrics: {stats['metrics']} numbers extracted, {stats['needs_review']} need review")
    return stats


def _extract(ctx: Ctx, data: bytes, mime: str, upload: dict[str, Any]) -> dict[str, Any]:
    recent = [{"id": p["id"], "platform": p["platform"], "posted": p["posted_at"][:10],
               "opening": textutil.truncate(p["final_text"], 120)}
              for p in ctx.store.select("posts", order="posted_at DESC", limit=25)]
    prompt = prompting.render("metrics_vision", input_json={"recent_posts": recent, "note": upload.get("note")})
    req = LLMRequest(task="vision", system="You read analytics screenshots exactly. Never guess numbers.",
                     prompt=prompt, images=[(data, mime)], max_output_tokens=2000, personal=True,
                     prompt_version=prompting.version("metrics_vision"))
    out, _ = ctx.llm.call_json(req, _VisionOut)
    platform = out.platform if out.platform in ("linkedin", "x") else None
    n = review = 0
    for pm in out.posts:
        values = {f: getattr(pm, f) for f in FIELDS if getattr(pm, f) is not None}
        if not values:
            continue
        post_id, match_conf = match_post(ctx, platform, pm.text_snippet, pm.posted_date)
        extraction = max(0.0, min(1.0, float(pm.confidence)))
        confident = post_id is not None and match_conf >= 0.75 and extraction >= 0.6
        post = ctx.store.get("posts", post_id) if post_id else None
        ctx.store.insert("metrics", {
            "id": ids.new_id("met"), "post_id": post_id, "platform": (post or {}).get("platform") or platform,
            "captured_at": timeutil.now_iso(), **values, "source": "screenshot", "upload_id": upload["id"],
            "extraction_confidence": round(extraction, 3), "match_confidence": match_conf,
            "status": "confirmed" if confident else "needs_review",
            "raw": pm.model_dump(), "created_at": timeutil.now_iso(),
            "notes": None if confident else ("Couldn't tell which post this is" if not post_id else
                                             "Low-confidence match: please confirm"),
        })
        n += 1
        review += 0 if confident else 1
    if out.account and platform and (out.account.followers is not None or out.account.profile_views is not None):
        date = ctx.local_date_str()
        ctx.store.upsert("account_stats", {"id": f"acs_{platform}_{date}", "date": date, "platform": platform,
                                           "followers": out.account.followers,
                                           "profile_views": out.account.profile_views, "source": "screenshot",
                                           "created_at": timeutil.now_iso()})
    return {"metrics": n, "needs_review": review, "platform": platform}

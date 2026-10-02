"""Typed settings: code defaults (pbs/defaults/settings.yaml) deep-merged with Ankit's overrides.

Overrides live in the private data repo (table `settings`, key `overrides`). Loading is tolerant: an
override that no longer validates is dropped with a warning instead of breaking the run. Applying a
new patch from the desk is strict: an invalid patch is rejected and the desk shows why.
"""

from __future__ import annotations

import copy
from functools import cache
from importlib import resources
from typing import Any, Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Platform = Literal["linkedin", "x"]
PLATFORMS: tuple[str, ...] = ("linkedin", "x")
Mode = Literal["external", "interview"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Delivery(_Strict):
    earliest_local_time: str = "01:00"
    latest_local_time: str = "21:00"
    weekly_batch_day: str = "saturday"
    weekly_batch_local_time: str = "19:00"
    reflection_fallback_day: str = "monday"
    reflection_fallback_local_time: str = "05:00"

    @field_validator("earliest_local_time", "latest_local_time", "weekly_batch_local_time",
                     "reflection_fallback_local_time")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        h, m = v.split(":")
        if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
            raise ValueError("time must be HH:MM")
        return f"{int(h):02d}:{int(m):02d}"

    @field_validator("weekly_batch_day", "reflection_fallback_day")
    @classmethod
    def _day(cls, v: str) -> str:
        v = v.lower()
        if v not in WEEKDAYS:
            raise ValueError(f"day must be one of {', '.join(WEEKDAYS)}")
        return v


WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class LinkedInPlatform(_Strict):
    enabled: bool = True
    slots: int = Field(3, ge=1, le=6)
    min_slots: int = Field(2, ge=1, le=6)
    max_interview_per_day: int = Field(1, ge=0, le=3)
    char_limit: int = Field(3000, ge=500, le=3000)
    fold_chars: int = Field(210, ge=80, le=400)


class XPlatform(_Strict):
    enabled: bool = True
    slots: int = Field(6, ge=1, le=10)
    min_slots: int = Field(4, ge=1, le=10)
    max_interview_per_day: int = Field(1, ge=0, le=3)
    premium: bool = False
    char_limit: int = Field(280, ge=100, le=280)
    premium_char_limit: int = Field(25000, ge=280, le=25000)
    thread_min: int = Field(3, ge=2, le=10)
    thread_max: int = Field(7, ge=2, le=15)
    reply_slots: int = Field(2, ge=0, le=6)
    reply_until_followers: int = Field(500, ge=0)


class Platforms(_Strict):
    linkedin: LinkedInPlatform = LinkedInPlatform()
    x: XPlatform = XPlatform()


class FormatSpec(_Strict):
    label: str
    platform: Platform
    prior: float = Field(0.5, gt=0.0, lt=1.0)


class Pillar(_Strict):
    label: str
    weight: float = Field(ge=0.0, le=1.0)
    mode: Mode = "external"
    formats: list[str]
    scouts: list[str] = []
    description: str = ""
    keywords: list[str] = []


class Affairs(_Strict):
    types: dict[str, str]
    linkedin_allowed_topics: list[str] = []


class Hooks(_Strict):
    types: list[str]


class Scouting(_Strict):
    concurrency: int = Field(8, ge=1, le=32)
    timeout_seconds: float = Field(20, ge=3, le=120)
    max_items_per_source: int = Field(40, ge=5, le=200)
    item_retention_days: int = Field(45, ge=7, le=365)
    dedup_window_days: int = Field(7, ge=1, le=60)
    lookback_hours: dict[str, int]
    cluster_threshold: float = Field(0.32, ge=0.1, le=0.9)
    shortlist_per_platform: int = Field(12, ge=3, le=40)
    candidates_per_scout: dict[str, int]
    per_source_cap: int = Field(8, ge=1, le=100)
    pause_after_failure_days: int = Field(7, ge=1, le=90)
    pause_after_zero_yield_weeks: int = Field(4, ge=1, le=52)
    user_agent: str


class Ranking(_Strict):
    novelty_window_days: int = 30
    resuggest_block_days: int = 3
    diversity_arm_penalty: float = Field(0.7, ge=0.1, le=1.0)
    weights: dict[str, float]
    timeliness_half_life_hours: dict[str, float]


class Learning(_Strict):
    frozen: bool = False
    half_life_days: float = Field(42, ge=3, le=365)
    prior_strength: float = Field(4, ge=0.5, le=50)
    explore_rate: float = Field(0.2, ge=0.0, le=0.8)
    explore_rate_cold_start: float = Field(0.3, ge=0.0, le=0.9)
    cold_start_days: int = Field(14, ge=0, le=120)
    metrics_min_posts: int = Field(10, ge=1, le=200)
    median_window: int = Field(20, ge=3, le=200)
    perf_blend: float = Field(0.4, ge=0.0, le=1.0)
    expired_value: float = Field(0.2, ge=0.0, le=1.0)
    skip_values: dict[str, float | None]
    edit_ratio_review_weeks: int = 4


class HashtagRange(_Strict):
    min: int = Field(0, ge=0, le=10)
    max: int = Field(3, ge=0, le=10)


class Hashtags(_Strict):
    enabled: bool = True
    linkedin: HashtagRange = HashtagRange(min=3, max=5)
    x: HashtagRange = HashtagRange(min=0, max=2)
    avoid: list[str] = []

    def range(self, platform: str) -> HashtagRange:
        return getattr(self, platform)


class Visuals(_Strict):
    enabled: bool = True
    name_linkedin: str = Field("", max_length=60)
    name_x: str = Field("", max_length=60)
    accent: str = Field("#4F46E5", pattern=r"^#[0-9a-fA-F]{6}$")


class Images(_Strict):
    """AI images for visuals (pbs/images.py). Each provider is used only when its secret is set: Cloudflare
    Workers AI is free (a daily allowance of about 60 images); Gemini and xAI images are paid per image."""
    enabled: bool = True
    providers: list[Literal["cloudflare", "gemini_image", "xai"]] = ["cloudflare", "gemini_image", "xai"]
    daily_limit: int = Field(20, ge=0, le=200)
    cloudflare_models: list[str] = ["@cf/black-forest-labs/flux-2-klein-4b", "@cf/black-forest-labs/flux-1-schnell"]
    gemini_models: list[str] = ["gemini-2.5-flash-image", "gemini-3.1-flash-image-preview"]
    xai_model: str = "grok-imagine-image"
    # Added to every image prompt: the house look, and no words (the desk draws the words, exactly).
    style: str = Field("clean editorial illustration, flat shapes with soft gradients and gentle depth, a calm "
                       "limited palette, generous empty space, modern and professional", max_length=400)


class Drafting(_Strict):
    interview_draft_now: bool = True
    questions_per_card: int = Field(2, ge=1, le=3)
    source_search_days: int = Field(30, ge=3, le=90)
    # The editor pass (editing.py): one more call per draft that reads as AI-written, rewriting just those parts.
    editor_pass: bool = True
    editor_max_per_run: int = Field(12, ge=0, le=40)
    # Model calls kept for drafts: at or below this many left, the pass is skipped, so it never costs a run's later
    # drafts their calls (12 is more than the most drafts one run makes).
    editor_reserve: int = Field(12, ge=0, le=50)


class Expiry(_Strict):
    interview_days: int = Field(7, ge=1, le=30)
    evergreen_days: int = Field(7, ge=1, le=30)
    request_days: int = Field(3, ge=1, le=30)
    editing_idle_hours: int = Field(72, ge=6, le=720)


class WeeklyBatch(_Strict):
    interview_cards: dict[str, int]
    evergreen_cards: dict[str, int]


class ProviderSpec(_Strict):
    kind: Literal["gemini", "openai", "fake"]
    # A model ID, or for Gemini "auto:flash" / "auto:flash-lite": the newest models of that family the key
    # can use, found at run time, so retired and renamed models don't break the pipeline.
    model: str
    # Tried in order when the model is retired or (with quota_per_model) reaches its daily quota.
    fallback_models: list[str] = []
    quota_per_model: bool = False
    api_key_env: str = ""
    base_url: str | None = None
    daily_limit: int = Field(100, ge=0)
    rpm: int = Field(10, ge=1)
    max_input_tokens: int | None = None
    # Extra output tokens for models that reason before answering (the reasoning counts as output).
    output_headroom: int = Field(0, ge=0, le=32000)
    # Provider-specific request fields (for example {"reasoning_effort": "low"}); dropped if rejected.
    extra_body: dict[str, Any] = {}
    trains_on_inputs: bool = True
    vision: bool = False
    grounding: bool = False


class LLM(_Strict):
    daily_cap: int = Field(60, ge=0, le=2000)
    max_calls_per_run: int = Field(45, ge=1, le=500)
    personal_allow_training_fallback: bool = True
    providers: dict[str, ProviderSpec]
    routes: dict[str, list[str]]
    temperature: dict[str, float] = {}

    @model_validator(mode="after")
    def _routes_exist(self) -> LLM:
        for task, chain in self.routes.items():
            missing = [p for p in chain if p not in self.providers]
            if missing:
                raise ValueError(f"route '{task}' uses unknown providers: {', '.join(missing)}")
        return self


class Notify(_Strict):
    on_delivery: bool = True
    on_request_done: bool = True
    on_failure: bool = True
    desk_url: str = ""


class Voice(_Strict):
    examples_per_prompt: int = Field(3, ge=0, le=5)
    avoid_phrases: list[str] = []
    bait_phrases: list[str] = []


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timezone: str = "Australia/Melbourne"
    display_name: str = "Ankit"
    delivery: Delivery = Delivery()
    platforms: Platforms = Platforms()
    formats: dict[str, FormatSpec]
    strategy: dict[str, dict[str, Pillar]]
    affairs: Affairs
    hooks: Hooks
    watchlist: dict[str, list[str]] = {}
    scouting: Scouting
    ranking: Ranking
    learning: Learning
    rewards: dict[str, dict[str, float]]
    expiry: Expiry = Expiry()
    drafting: Drafting = Drafting()
    hashtags: Hashtags = Hashtags()
    visuals: Visuals = Visuals()
    images: Images = Images()
    weekly_batch: WeeklyBatch
    llm: LLM
    notify: Notify = Notify()
    voice: Voice = Voice()
    profile: str = ""

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        ZoneInfo(v)
        return v

    @model_validator(mode="after")
    def _consistency(self) -> Settings:
        for platform in PLATFORMS:
            if platform not in self.strategy or not self.strategy[platform]:
                raise ValueError(f"strategy needs at least one pillar for {platform}")
            for key, pillar in self.strategy[platform].items():
                bad = [f for f in pillar.formats if f not in self.formats or self.formats[f].platform != platform]
                if bad:
                    raise ValueError(f"pillar {platform}.{key} has formats not valid on {platform}: {bad}")
        if self.platforms.linkedin.min_slots > self.platforms.linkedin.slots:
            raise ValueError("linkedin min_slots cannot exceed slots")
        if self.platforms.x.min_slots > self.platforms.x.slots:
            raise ValueError("x min_slots cannot exceed slots")
        if self.platforms.x.thread_min > self.platforms.x.thread_max:
            raise ValueError("x thread_min cannot exceed thread_max")
        return self

    # -- convenience -------------------------------------------------------------------------
    def pillars(self, platform: str) -> dict[str, Pillar]:
        return self.strategy.get(platform, {})

    def pillar(self, platform: str, key: str) -> Pillar | None:
        return self.strategy.get(platform, {}).get(key)

    def normalized_weights(self, platform: str) -> dict[str, float]:
        pillars = self.pillars(platform)
        total = sum(p.weight for p in pillars.values()) or 1.0
        return {k: p.weight / total for k, p in pillars.items()}

    def platform_enabled(self, platform: str) -> bool:
        return bool(getattr(self.platforms, platform).enabled)

    def slots(self, platform: str) -> int:
        return int(getattr(self.platforms, platform).slots)

    def x_char_limit(self) -> int:
        x = self.platforms.x
        return x.premium_char_limit if x.premium else x.char_limit


# ---------------------------------------------------------------------------
# Loading and merging
# ---------------------------------------------------------------------------


@cache
def default_dict() -> dict[str, Any]:
    text = resources.files("pbs.defaults").joinpath("settings.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    data["profile"] = resources.files("pbs.defaults").joinpath("profile.md").read_text(encoding="utf-8")
    voice = yaml.safe_load(resources.files("pbs.defaults").joinpath("voice.yaml").read_text(encoding="utf-8"))
    data["voice"] = voice
    return data


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Recursive merge. Lists and scalars in `patch` replace; `None` removes the override."""
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if value is None:
            out.pop(key, None)
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _flatten(patch: dict[str, Any], prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    items: list[tuple[tuple[str, ...], Any]] = []
    for key, value in patch.items():
        if isinstance(value, dict) and value:
            items.extend(_flatten(value, prefix + (key,)))
        else:
            items.append((prefix + (key,), value))
    return items


def _nest(path: tuple[str, ...], value: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    cur = out
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = value
    return out


def load(overrides: dict[str, Any] | None = None) -> tuple[Settings, list[str]]:
    """Return effective settings and warnings about overrides that were dropped."""
    base = default_dict()
    overrides = overrides or {}
    merged = deep_merge(base, overrides)
    try:
        return Settings.model_validate(merged), []
    except ValidationError:
        pass
    # Apply overrides one leaf at a time, keeping those that validate.
    warnings: list[str] = []
    current = copy.deepcopy(base)
    for path, value in _flatten(overrides):
        candidate = deep_merge(current, _nest(path, value))
        try:
            Settings.model_validate(candidate)
            current = candidate
        except ValidationError as exc:
            warnings.append(f"ignored setting {'.'.join(path)}: {exc.errors()[0].get('msg', 'invalid')}")
    return Settings.model_validate(current), warnings


def _unknown_keys(patch: dict[str, Any], reference: dict[str, Any], prefix: str = "") -> list[str]:
    """Keys in patch that don't exist in the reference (open maps are allowed to grow)."""
    open_maps = {"strategy", "strategy.linkedin", "strategy.x", "llm.providers", "llm.routes",
                 "llm.temperature", "watchlist", "formats", "rewards.linkedin", "rewards.x",
                 "scouting.lookback_hours", "scouting.candidates_per_scout", "affairs.types",
                 "learning.skip_values", "ranking.timeliness_half_life_hours"}
    unknown: list[str] = []
    for key, value in patch.items():
        path = f"{prefix}.{key}" if prefix else key
        if prefix in open_maps:
            continue
        if key not in reference:
            unknown.append(path)
        elif isinstance(value, dict) and isinstance(reference.get(key), dict):
            unknown.extend(_unknown_keys(value, reference[key], path))
    return unknown


def validate_patch(current_overrides: dict[str, Any], patch: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Strictly validate a patch from the desk. Returns (new_overrides, error)."""
    unknown = _unknown_keys(patch, default_dict())
    if unknown:
        return current_overrides, f"unknown setting(s): {', '.join(unknown)}"
    new_overrides = deep_merge(current_overrides, patch)
    # `None` in a patch resets to default, so drop it from the stored overrides entirely.
    try:
        Settings.model_validate(deep_merge(default_dict(), new_overrides))
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ()))
        return current_overrides, f"{where}: {first.get('msg', 'invalid value')}"
    return new_overrides, None

"""The contract between the pipeline and the desk.

- Inbox events: what the desk writes to `inbox/` (strictly validated, one event at a time).
- Desk state: what the pipeline exports to `desk/desk.json` for the desk to render.

`pbs schema` writes the JSON Schema that generates web/src/types/contracts.ts, so both sides share
one definition. Bump DESK_SCHEMA_VERSION on breaking changes.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

DESK_SCHEMA_VERSION = 1

PlatformName = Literal["linkedin", "x"]
CardStatus = Literal["drafting", "suggested", "needs_input", "editing", "posted", "skipped", "expired",
                     "blocked", "failed"]
CardKind = Literal["news", "evergreen", "interview", "request", "adapt"]
FormatName = Literal["li_text", "x_single", "x_thread", "x_quote", "x_reply"]
SkipReason = Literal["not_interesting", "off_brand", "wrong_timing", "too_risky", "already_covered", "other"]
Tier = Literal["world", "india", "bihar", "other"]


class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Card pieces
# ---------------------------------------------------------------------------


class Hook(_Out):
    type: str = "observation"
    text: str


class SourceRef(_Out):
    url: str
    title: str = ""
    publisher: str | None = None
    lang: str = "en"
    published_at: str | None = None
    orig_title: str | None = None
    summary: str | None = None


class Claim(_Out):
    text: str
    source: int | None = Field(None, description="Index into the card's sources (0-based)")


class ReplyTarget(_Out):
    context: str = ""
    search_terms: list[str] = []
    accounts: list[str] = []


class Draft(_Out):
    text: str = ""
    posts: list[str] = []
    quote_url: str | None = None
    reply: ReplyTarget | None = None


class Flags(_Out):
    blocked: list[str] = []
    unsourced: list[str] = []
    first_person: list[str] = []
    opinion: list[str] = []
    sensitive: bool = False
    sensitive_reason: str | None = None
    avoid_phrases: list[str] = []
    bait: list[str] = []
    length: list[str] = []
    stance_id: str | None = None
    notes: list[str] = []


class Question(_Out):
    id: str
    q: str
    why: str | None = None
    kind: str | None = None


class Answer(_Out):
    question_id: str
    answer: str
    at: str | None = None


class Work(_Out):
    kind: Literal["draft", "rewrite", "questions"]
    note: str | None = None
    chips: list[str] = []
    requested_at: str | None = None
    attempts: int = 0
    last_error: str | None = None
    target_platform: PlatformName | None = None
    target_format: FormatName | None = None


class Working(_Out):
    text: str | None = None
    posts: list[str] | None = None
    hook_index: int | None = None
    hooks: list[Hook] | None = Field(None, description="The openings as he edited them (same order; his own added last)")
    updated_at: str | None = None


class Skip(_Out):
    reason: SkipReason
    note: str | None = None
    at: str | None = None


class Versions(_Out):
    playbook: str | None = None
    prompt: str | None = None
    voice: str | None = None


class LLMInfo(_Out):
    provider: str | None = None
    model: str | None = None


class Card(_Out):
    id: str
    topic_id: str | None = None
    request_id: str | None = None
    delivery_id: str | None = None
    kind: CardKind = "news"
    platform: PlatformName
    mode: Literal["external", "interview"] = "external"
    pillar: str
    format: FormatName
    affairs_type: str | None = None
    issue_key: str | None = None
    title: str
    why_now: str | None = None
    angle: str | None = None
    format_note: str | None = None
    draft: Draft | None = None
    draft_original: Draft | None = None
    hooks: list[Hook] = []
    hook_type: str | None = None
    sources: list[SourceRef] = []
    claims: list[Claim] = []
    flags: Flags = Flags()
    questions: list[Question] = []
    answers: list[Answer] = []
    status: CardStatus
    rank: int | None = None
    score: float | None = None
    score_parts: dict[str, Any] = {}
    explore: bool = False
    experiment_id: str | None = None
    arm: str | None = None
    versions: Versions = Versions()
    llm: LLMInfo | None = None
    work: Work | None = None
    working: Working | None = None
    skip: Skip | None = None
    rewrite_count: int = 0
    delivered_at: str | None = None
    expires_at: str | None = None
    status_changed_at: str | None = None
    post_id: str | None = None
    draft_state: Literal["full", "brief", "pending"] = "full"
    draft_basis: Literal["sources", "answers"] | None = Field(
        None, description="What the current draft was written from: recent sources, or his answers (plus sources)")
    created_at: str
    updated_at: str | None = None
    revision: int = 0


# ---------------------------------------------------------------------------
# Other entities exported to the desk
# ---------------------------------------------------------------------------


class Metric(_Out):
    id: str
    post_id: str | None = None
    platform: PlatformName | None = None
    captured_at: str | None = None
    impressions: int | None = None
    reactions: int | None = None
    comments: int | None = None
    reposts: int | None = None
    sends: int | None = None
    followers_gained: int | None = None
    profile_views: int | None = None
    link_clicks: int | None = None
    source: Literal["manual", "screenshot", "csv"] = "manual"
    upload_id: str | None = None
    extraction_confidence: float | None = None
    match_confidence: float | None = None
    status: Literal["confirmed", "needs_review", "rejected"] = "confirmed"
    notes: str | None = None
    raw: dict[str, Any] | None = None
    created_at: str | None = None


class Post(_Out):
    id: str
    card_id: str
    platform: PlatformName
    pillar: str | None = None
    format: str | None = None
    title: str | None = None
    final_text: str = ""
    final_posts: list[str] = []
    posted_at: str
    post_url: str | None = None
    edit_ratio: float | None = None
    edit_stats: dict[str, Any] = {}
    hook_used: dict[str, Any] | None = None
    features: dict[str, Any] = {}
    editing_seconds: int | None = None
    time_to_post_minutes: float | None = None
    reward: float | None = None
    reward_parts: dict[str, Any] = {}
    guard: dict[str, Any] = {}
    latest_metrics: Metric | None = None


class MetricUpload(_Out):
    id: str
    paths: list[str] = []
    week: str | None = None
    note: str | None = None
    status: Literal["pending", "processed", "failed"] = "pending"
    created_at: str | None = None
    processed_at: str | None = None
    results: dict[str, Any] | None = None
    error: str | None = None


class AccountStat(_Out):
    id: str
    date: str
    platform: PlatformName
    followers: int | None = None
    profile_views: int | None = None
    source: str | None = None


class Position(_Out):
    key: str
    label: str
    text: str


class StanceChoice(_Out):
    position_key: str | None = None
    custom_text: str | None = None


class Stance(_Out):
    id: str
    issue: str
    tier: Tier = "other"
    context: str | None = None
    positions: list[Position] = []
    chosen: StanceChoice | None = None
    status: Literal["proposed", "active", "archived"] = "proposed"
    sources: list[SourceRef] = []
    keywords: list[str] = []
    created_by: str | None = None
    updated_at: str | None = None


class Request(_Out):
    id: str
    query: str
    platforms: dict[str, int] = {}
    notes: str | None = None
    status: Literal["queued", "running", "done", "partial", "failed", "cancelled"] = "queued"
    created_at: str | None = None
    completed_at: str | None = None
    card_ids: list[str] = []
    error: str | None = None
    search: dict[str, Any] | None = Field(None, description="What the search understood and found: interpretation, "
                                          "queries, exclude, recency_days, results, kept, checked, items")


class SourceHealth(_Out):
    last_fetch_at: str | None = None
    last_success_at: str | None = None
    consecutive_failures: int = 0
    last_error: str | None = None
    items_last_run: int | None = None
    items_total: int | None = None


class Source(_Out):
    id: str
    name: str
    kind: str
    url: str | None = None
    query: str | None = None
    scout: str
    tier: str | None = None
    lang: str = "en"
    active: bool = True
    paused_reason: str | None = None
    added_by: str | None = None
    best_effort: bool = False
    health: SourceHealth = SourceHealth()
    yield_stats: dict[str, Any] = {}


class Proposal(_Out):
    id: str
    kind: str
    title: str
    detail: str | None = None
    payload: dict[str, Any] = {}
    evidence: list[str] = []
    confidence: Literal["low", "medium", "high"] = "medium"
    status: Literal["pending", "approved", "rejected", "applied"] = "pending"
    created_at: str | None = None
    decided_at: str | None = None
    decision_note: str | None = None
    source: str | None = None


class PlaybookRule(_Out):
    id: str
    text: str
    platform: PlatformName | None = None
    pillar: str | None = None
    confidence: Literal["low", "medium", "high"] = "medium"
    evidence: list[str] = []
    reversal: str | None = None
    source: Literal["seed", "reflection", "user", "voice"] = "seed"
    added_in: str | None = None


class Playbook(_Out):
    id: str
    version: int
    created_at: str
    status: Literal["active", "retired"] = "active"
    rules: list[PlaybookRule] = []
    changes: list[dict[str, Any]] = []
    experiments: list[str] = []
    summary: str | None = None
    source: str | None = None


class Experiment(_Out):
    id: str
    created_at: str
    platform: PlatformName | None = None
    pillar: str | None = None
    instruction: str
    hypothesis: str | None = None
    status: Literal["active", "promoted", "retired"] = "active"
    trials: int = 0
    picks: int = 0
    stats: dict[str, Any] = {}


class SystemReport(_Out):
    id: str
    week: str
    created_at: str
    period: dict[str, Any] = {}
    sections: dict[str, Any] = {}
    actions: list[dict[str, Any]] = []
    proposals: list[str] = []


class VoiceProfile(_Out):
    id: str
    version: int
    created_at: str
    stats: dict[str, Any] = {}
    rules: list[str] = []
    avoid: list[str] = []
    cut_phrases: list[dict[str, Any]] = []
    added_phrases: list[dict[str, Any]] = []
    examples: dict[str, list[str]] = {}
    summary: str | None = None


class Arm(_Out):
    id: str
    platform: PlatformName
    pillar: str
    format: str
    alpha: float
    beta: float
    mean: float
    n_obs: float
    prior_mean: float


class RunError(_Out):
    where: str
    type: str
    message: str | None = None
    at: str | None = None


class Run(_Out):
    id: str
    task: str
    trigger: str | None = None
    started_at: str
    ended_at: str | None = None
    status: Literal["running", "ok", "partial", "failed"] = "ok"
    steps: list[dict[str, Any]] = []
    llm: dict[str, Any] = {}
    errors: list[RunError] = []
    degraded: str | None = None
    notes: list[str] = []


class Quota(_Out):
    provider: str
    day: str
    requests: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    daily_limit: int | None = None
    exhausted_at: str | None = None
    last_error: str | None = None
    last_error_at: str | None = None
    last_ok_at: str | None = None
    model: str | None = None


class DeskWarning(_Out):
    level: Literal["info", "warn", "error"] = "warn"
    code: str
    message: str
    at: str | None = None


class DeliveryInfo(_Out):
    id: str
    local_date: str
    delivered_at: str | None = None
    counts: dict[str, int] = {}
    degraded: str | None = None
    notes: list[str] = []
    kind: str | None = None


class RejectedEvent(_Out):
    id: str
    type: str | None = None
    error: str | None = None
    at: str | None = None


class DoctorCheck(_Out):
    name: str
    status: Literal["ok", "warn", "fail", "skip"]
    detail: str | None = None


class DoctorReport(_Out):
    id: str
    created_at: str
    checks: list[DoctorCheck] = []
    summary: dict[str, Any] = {}


class DeskMeta(_Out):
    schema_version: int = DESK_SCHEMA_VERSION
    generated_at: str
    run_id: str | None = None
    app_version: str
    timezone: str
    display_name: str
    next_delivery_local: str | None = None


class DeskState(_Out):
    meta: DeskMeta
    settings: dict[str, Any]
    settings_overrides: dict[str, Any] = {}
    delivery: DeliveryInfo | None = None
    cards: list[Card] = []
    posts: list[Post] = []
    metrics: list[Metric] = []
    uploads: list[MetricUpload] = []
    account_stats: list[AccountStat] = []
    stances: list[Stance] = []
    requests: list[Request] = []
    sources: list[Source] = []
    proposals: list[Proposal] = []
    playbook: Playbook | None = None
    playbook_history: list[Playbook] = []
    experiments: list[Experiment] = []
    report: SystemReport | None = None
    reports_index: list[dict[str, str]] = []
    voice: VoiceProfile | None = None
    arms: list[Arm] = []
    runs: list[Run] = []
    quota: list[Quota] = []
    warnings: list[DeskWarning] = []
    stats: dict[str, Any] = {}
    rejected_events: list[RejectedEvent] = []
    processed_event_ids: list[str] = []
    doctor: DoctorReport | None = None
    archive_months: list[str] = []


# ---------------------------------------------------------------------------
# Inbox events (desk -> pipeline)
# ---------------------------------------------------------------------------


class _Event(_In):
    id: str = Field(min_length=1, max_length=80)
    at: str


class CardStatusEvent(_Event):
    type: Literal["card.status"]
    card_id: str
    status: Literal["editing", "suggested"]


class HookIn(_In):
    type: str = Field("observation", max_length=24)
    text: str = Field(max_length=600)


class CardEditEvent(_Event):
    type: Literal["card.edit"]
    card_id: str
    text: str | None = Field(None, max_length=30000)
    posts: list[Annotated[str, Field(max_length=30000)]] | None = Field(None, max_length=25)
    hook_index: int | None = None
    hooks: list[HookIn] | None = Field(None, max_length=10)


class CardPostedEvent(_Event):
    type: Literal["card.posted"]
    card_id: str
    text: str | None = Field(None, max_length=30000)
    posts: list[Annotated[str, Field(max_length=30000)]] | None = Field(None, max_length=25)
    post_url: str | None = Field(None, max_length=500)
    posted_at: str | None = None
    editing_seconds: int | None = Field(None, ge=0, le=86400)
    hook_index: int | None = None


class CardSkipEvent(_Event):
    type: Literal["card.skip"]
    card_id: str
    reason: SkipReason
    note: str | None = Field(None, max_length=1000)


class CardRewriteEvent(_Event):
    type: Literal["card.rewrite"]
    card_id: str
    note: str = Field("", max_length=1000)
    chips: list[str] = Field([], max_length=10)
    target_platform: PlatformName | None = None
    target_format: FormatName | None = None


class AnswerIn(_In):
    question_id: str
    answer: str = Field(max_length=6000)


class StanceFromAnswer(_In):
    stance_id: str | None = None
    issue: str | None = Field(None, max_length=200)
    tier: Tier | None = None
    text: str = Field(max_length=1000)


class CardAnswersEvent(_Event):
    type: Literal["card.answers"]
    card_id: str
    answers: list[AnswerIn] = Field(min_length=1, max_length=10)
    reusable: bool = True
    save_as_stance: StanceFromAnswer | None = None


class CardRestoreEvent(_Event):
    type: Literal["card.restore"]
    card_id: str


class CardDraftNowEvent(_Event):
    type: Literal["card.draft_now"]
    card_id: str


class CardHookEvent(_Event):
    type: Literal["card.hook"]
    card_id: str
    hook_index: int = Field(ge=0, le=10)
    text: str | None = Field(None, max_length=600)


class PostUpdateEvent(_Event):
    type: Literal["post.update"]
    post_id: str
    post_url: str | None = Field(None, max_length=500)
    text: str | None = Field(None, max_length=30000)
    posts: list[Annotated[str, Field(max_length=30000)]] | None = Field(None, max_length=25)
    posted_at: str | None = None


class MetricValues(_In):
    impressions: int | None = Field(None, ge=0)
    reactions: int | None = Field(None, ge=0)
    comments: int | None = Field(None, ge=0)
    reposts: int | None = Field(None, ge=0)
    sends: int | None = Field(None, ge=0)
    followers_gained: int | None = Field(None, ge=0)
    profile_views: int | None = Field(None, ge=0)
    link_clicks: int | None = Field(None, ge=0)


class PostMetricsEvent(_Event):
    type: Literal["post.metrics"]
    post_id: str
    captured_at: str | None = None
    values: MetricValues


class MetricsUploadEvent(_Event):
    type: Literal["metrics.upload"]
    upload_id: str
    paths: list[str] = Field(min_length=1, max_length=20)
    week: str | None = None
    note: str | None = Field(None, max_length=1000)


class MetricsReviewEvent(_Event):
    type: Literal["metrics.review"]
    metric_id: str
    action: Literal["confirm", "reject", "edit"]
    post_id: str | None = None
    values: MetricValues | None = None


class AccountStatsEvent(_Event):
    type: Literal["account.stats"]
    date: str
    platform: PlatformName
    followers: int | None = Field(None, ge=0)
    profile_views: int | None = Field(None, ge=0)


class RequestCreateEvent(_Event):
    type: Literal["request.create"]
    request_id: str
    query: str = Field(min_length=2, max_length=500)
    platforms: dict[PlatformName, Annotated[int, Field(ge=0, le=5)]]
    notes: str | None = Field(None, max_length=2000)


class RequestCancelEvent(_Event):
    type: Literal["request.cancel"]
    request_id: str


class PositionIn(_In):
    key: str = Field(max_length=40)
    label: str = Field(max_length=120)
    text: str = Field(max_length=1000)


class StanceUpsertEvent(_Event):
    type: Literal["stance.upsert"]
    stance_id: str
    issue: str | None = Field(None, max_length=200)
    tier: Tier | None = None
    context: str | None = Field(None, max_length=2000)
    positions: list[PositionIn] | None = Field(None, max_length=8)
    chosen_key: str | None = None
    custom_text: str | None = Field(None, max_length=1000)
    clear_choice: bool = False
    status: Literal["proposed", "active", "archived"] | None = None
    keywords: list[str] | None = Field(None, max_length=30)


class StanceDeleteEvent(_Event):
    type: Literal["stance.delete"]
    stance_id: str


class StanceProposeEvent(_Event):
    type: Literal["stance.propose"]
    count: int = Field(3, ge=1, le=10)


class SourceUpsertEvent(_Event):
    type: Literal["source.upsert"]
    source_id: str
    name: str | None = Field(None, max_length=120)
    kind: Literal["rss", "gnews", "arxiv", "hf_papers", "hn_front", "hn_show", "wikipedia_otd", "reddit"] | None = None
    url: str | None = Field(None, max_length=1000)
    query: str | None = Field(None, max_length=300)
    scout: Literal["tech", "affairs", "startups", "life"] | None = None
    tier: Tier | None = None
    lang: Literal["en", "hi"] | None = None
    active: bool | None = None
    pillar_hints: list[str] | None = None


class SourceDeleteEvent(_Event):
    type: Literal["source.delete"]
    source_id: str


class SettingsUpdateEvent(_Event):
    type: Literal["settings.update"]
    patch: dict[str, Any]


class ProfileUpdateEvent(_Event):
    type: Literal["profile.update"]
    text: str = Field(max_length=8000)


class ProposalDecideEvent(_Event):
    type: Literal["proposal.decide"]
    proposal_id: str
    decision: Literal["approve", "reject"]
    note: str | None = Field(None, max_length=1000)


class PlaybookRuleEvent(_Event):
    type: Literal["playbook.rule"]
    action: Literal["add", "remove", "edit"]
    rule_id: str | None = None
    text: str | None = Field(None, max_length=600)
    platform: PlatformName | None = None
    pillar: str | None = None


class RunRequestEvent(_Event):
    type: Literal["run.request"]
    tasks: list[Literal["morning", "weekly_batch", "reflection", "doctor", "report", "scout"]] = []
    force: bool = False


InboxEvent = Annotated[
    CardStatusEvent | CardEditEvent | CardPostedEvent | CardSkipEvent | CardRewriteEvent | CardAnswersEvent
    | CardRestoreEvent | CardDraftNowEvent | CardHookEvent | PostUpdateEvent | PostMetricsEvent
    | MetricsUploadEvent | MetricsReviewEvent | AccountStatsEvent | RequestCreateEvent | RequestCancelEvent
    | StanceUpsertEvent | StanceDeleteEvent | StanceProposeEvent | SourceUpsertEvent | SourceDeleteEvent
    | SettingsUpdateEvent | ProfileUpdateEvent | ProposalDecideEvent | PlaybookRuleEvent | RunRequestEvent,
    Field(discriminator="type"),
]

EVENT_ADAPTER: TypeAdapter[Any] = TypeAdapter(InboxEvent)


class InboxBatch(_In):
    v: Literal[1] = 1
    id: str
    device: str | None = None
    created_at: str
    events: list[InboxEvent]


class _BatchEnvelope(BaseModel):
    """Loose envelope so one bad event doesn't reject the whole batch."""

    model_config = ConfigDict(extra="ignore")
    v: int = 1
    id: str
    device: str | None = None
    created_at: str | None = None
    events: list[dict[str, Any]] = []


def parse_envelope(data: Any) -> _BatchEnvelope:
    return _BatchEnvelope.model_validate(data)


def parse_event(data: dict[str, Any]) -> Any:
    return EVENT_ADAPTER.validate_python(data)


def json_schema() -> dict[str, Any]:
    """Combined schema for TypeScript generation."""

    class Contracts(BaseModel):
        desk: DeskState
        batch: InboxBatch

    return Contracts.model_json_schema()

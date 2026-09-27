/* Generated from pbs/contracts.py by 'npm run gen:types'. Do not edit. */

export type CreatedAt = string;
export type Device = string | null;
export type At = string;
export type CardId = string;
export type Id = string;
export type Status = "editing" | "suggested";
export type Type = "card.status";
export type At1 = string;
export type CardId1 = string;
export type HookIndex = number | null;
export type Id1 = string;
export type Posts = string[] | null;
export type Text = string | null;
export type Type1 = "card.edit";
export type At2 = string;
export type CardId2 = string;
export type EditingSeconds = number | null;
export type HookIndex1 = number | null;
export type Id2 = string;
export type PostUrl = string | null;
export type PostedAt = string | null;
export type Posts1 = string[] | null;
export type Text1 = string | null;
export type Type2 = "card.posted";
export type At3 = string;
export type CardId3 = string;
export type Id3 = string;
export type Note = string | null;
export type Reason = "not_interesting" | "off_brand" | "wrong_timing" | "too_risky" | "already_covered" | "other";
export type Type3 = "card.skip";
export type At4 = string;
export type CardId4 = string;
/**
 * @maxItems 10
 */
export type Chips = string[];
export type Id4 = string;
export type Note1 = string;
export type TargetFormat = ("li_text" | "x_single" | "x_thread" | "x_quote" | "x_reply") | null;
export type TargetPlatform = ("linkedin" | "x") | null;
export type Type4 = "card.rewrite";
export type Answer = string;
export type QuestionId = string;
/**
 * @minItems 1
 * @maxItems 10
 */
export type Answers = AnswerIn[];
export type At5 = string;
export type CardId5 = string;
export type Id5 = string;
export type Reusable = boolean;
export type Issue = string | null;
export type StanceId = string | null;
export type Text2 = string;
export type Tier = ("world" | "india" | "bihar" | "other") | null;
export type Type5 = "card.answers";
export type At6 = string;
export type CardId6 = string;
export type Id6 = string;
export type Type6 = "card.restore";
export type At7 = string;
export type CardId7 = string;
export type Id7 = string;
export type Type7 = "card.draft_now";
export type At8 = string;
export type CardId8 = string;
export type HookIndex2 = number;
export type Id8 = string;
export type Type8 = "card.hook";
export type At9 = string;
export type Id9 = string;
export type PostId = string;
export type PostUrl1 = string | null;
export type PostedAt1 = string | null;
export type Posts2 = string[] | null;
export type Text3 = string | null;
export type Type9 = "post.update";
export type At10 = string;
export type CapturedAt = string | null;
export type Id10 = string;
export type PostId1 = string;
export type Type10 = "post.metrics";
export type Comments = number | null;
export type FollowersGained = number | null;
export type Impressions = number | null;
export type LinkClicks = number | null;
export type ProfileViews = number | null;
export type Reactions = number | null;
export type Reposts = number | null;
export type Sends = number | null;
export type At11 = string;
export type Id11 = string;
export type Note2 = string | null;
/**
 * @minItems 1
 * @maxItems 20
 */
export type Paths = string[];
export type Type11 = "metrics.upload";
export type UploadId = string;
export type Week = string | null;
export type Action = "confirm" | "reject" | "edit";
export type At12 = string;
export type Id12 = string;
export type MetricId = string;
export type PostId2 = string | null;
export type Type12 = "metrics.review";
export type At13 = string;
export type Date = string;
export type Followers = number | null;
export type Id13 = string;
export type Platform = "linkedin" | "x";
export type ProfileViews1 = number | null;
export type Type13 = "account.stats";
export type At14 = string;
export type Id14 = string;
export type Notes = string | null;
export type Query = string;
export type RequestId = string;
export type Type14 = "request.create";
export type At15 = string;
export type Id15 = string;
export type RequestId1 = string;
export type Type15 = "request.cancel";
export type At16 = string;
export type ChosenKey = string | null;
export type ClearChoice = boolean;
export type Context = string | null;
export type CustomText = string | null;
export type Id16 = string;
export type Issue1 = string | null;
export type Keywords = string[] | null;
export type Positions = PositionIn[] | null;
export type Key = string;
export type Label = string;
export type Text4 = string;
export type StanceId1 = string;
export type Status1 = ("proposed" | "active" | "archived") | null;
export type Tier1 = ("world" | "india" | "bihar" | "other") | null;
export type Type16 = "stance.upsert";
export type At17 = string;
export type Id17 = string;
export type StanceId2 = string;
export type Type17 = "stance.delete";
export type At18 = string;
export type Count = number;
export type Id18 = string;
export type Type18 = "stance.propose";
export type Active = boolean | null;
export type At19 = string;
export type Id19 = string;
export type Kind =
  ("rss" | "gnews" | "arxiv" | "hf_papers" | "hn_front" | "hn_show" | "wikipedia_otd" | "reddit") | null;
export type Lang = ("en" | "hi") | null;
export type Name = string | null;
export type PillarHints = string[] | null;
export type Query1 = string | null;
export type Scout = ("tech" | "affairs" | "startups" | "life") | null;
export type SourceId = string;
export type Tier2 = ("world" | "india" | "bihar" | "other") | null;
export type Type19 = "source.upsert";
export type Url = string | null;
export type At20 = string;
export type Id20 = string;
export type SourceId1 = string;
export type Type20 = "source.delete";
export type At21 = string;
export type Id21 = string;
export type Type21 = "settings.update";
export type At22 = string;
export type Id22 = string;
export type Text5 = string;
export type Type22 = "profile.update";
export type At23 = string;
export type Decision = "approve" | "reject";
export type Id23 = string;
export type Note3 = string | null;
export type ProposalId = string;
export type Type23 = "proposal.decide";
export type Action1 = "add" | "remove" | "edit";
export type At24 = string;
export type Id24 = string;
export type Pillar = string | null;
export type Platform1 = ("linkedin" | "x") | null;
export type RuleId = string | null;
export type Text6 = string | null;
export type Type24 = "playbook.rule";
export type At25 = string;
export type Force = boolean;
export type Id25 = string;
export type Tasks = ("morning" | "weekly_batch" | "reflection" | "doctor" | "report" | "scout")[];
export type Type25 = "run.request";
export type Events = (
  | CardStatusEvent
  | CardEditEvent
  | CardPostedEvent
  | CardSkipEvent
  | CardRewriteEvent
  | CardAnswersEvent
  | CardRestoreEvent
  | CardDraftNowEvent
  | CardHookEvent
  | PostUpdateEvent
  | PostMetricsEvent
  | MetricsUploadEvent
  | MetricsReviewEvent
  | AccountStatsEvent
  | RequestCreateEvent
  | RequestCancelEvent
  | StanceUpsertEvent
  | StanceDeleteEvent
  | StanceProposeEvent
  | SourceUpsertEvent
  | SourceDeleteEvent
  | SettingsUpdateEvent
  | ProfileUpdateEvent
  | ProposalDecideEvent
  | PlaybookRuleEvent
  | RunRequestEvent
)[];
export type Id26 = string;
export type V = 1;
export type Date1 = string;
export type Followers1 = number | null;
export type Id27 = string;
export type Platform2 = "linkedin" | "x";
export type ProfileViews2 = number | null;
export type Source = string | null;
export type AccountStats = AccountStat[];
export type ArchiveMonths = string[];
export type Alpha = number;
export type Beta = number;
export type Format = string;
export type Id28 = string;
export type Mean = number;
export type NObs = number;
export type Pillar1 = string;
export type Platform3 = "linkedin" | "x";
export type PriorMean = number;
export type Arms = Arm[];
export type AffairsType = string | null;
export type Angle = string | null;
export type Answer2 = string;
export type At26 = string | null;
export type QuestionId1 = string;
export type Answers1 = Answer1[];
export type Arm1 = string | null;
/**
 * Index into the card's sources (0-based)
 */
export type Source1 = number | null;
export type Text7 = string;
export type Claims = Claim[];
export type CreatedAt1 = string;
export type DeliveredAt = string | null;
export type DeliveryId = string | null;
export type Posts3 = string[];
export type QuoteUrl = string | null;
export type Accounts = string[];
export type Context1 = string;
export type SearchTerms = string[];
export type Text8 = string;
export type DraftState = "full" | "brief" | "pending";
export type ExperimentId = string | null;
export type ExpiresAt = string | null;
export type Explore = boolean;
export type AvoidPhrases = string[];
export type Bait = string[];
export type Blocked = string[];
export type FirstPerson = string[];
export type Length = string[];
export type Notes1 = string[];
export type Opinion = string[];
export type Sensitive = boolean;
export type SensitiveReason = string | null;
export type StanceId3 = string | null;
export type Unsourced = string[];
export type Format1 = "li_text" | "x_single" | "x_thread" | "x_quote" | "x_reply";
export type FormatNote = string | null;
export type HookType = string | null;
export type Text9 = string;
export type Type26 = string;
export type Hooks = Hook[];
export type Id29 = string;
export type IssueKey = string | null;
export type Kind1 = "news" | "evergreen" | "interview" | "request" | "adapt";
export type Model = string | null;
export type Provider = string | null;
export type Mode = "external" | "interview";
export type Pillar2 = string;
export type Platform4 = "linkedin" | "x";
export type PostId3 = string | null;
export type Id30 = string;
export type Kind2 = string | null;
export type Q = string;
export type Why = string | null;
export type Questions = Question[];
export type Rank = number | null;
export type RequestId2 = string | null;
export type Revision = number;
export type RewriteCount = number;
export type Score = number | null;
export type At27 = string | null;
export type Note4 = string | null;
export type Reason1 = "not_interesting" | "off_brand" | "wrong_timing" | "too_risky" | "already_covered" | "other";
export type Lang1 = string;
export type OrigTitle = string | null;
export type PublishedAt = string | null;
export type Publisher = string | null;
export type Summary = string | null;
export type Title = string;
export type Url1 = string;
export type Sources = SourceRef[];
export type Status2 =
  "drafting" | "suggested" | "needs_input" | "editing" | "posted" | "skipped" | "expired" | "blocked" | "failed";
export type StatusChangedAt = string | null;
export type Title1 = string;
export type TopicId = string | null;
export type UpdatedAt = string | null;
export type Playbook = string | null;
export type Prompt = string | null;
export type Voice = string | null;
export type WhyNow = string | null;
export type Attempts = number;
export type Chips1 = string[];
export type Kind3 = "draft" | "rewrite" | "questions";
export type LastError = string | null;
export type Note5 = string | null;
export type RequestedAt = string | null;
export type TargetFormat1 = ("li_text" | "x_single" | "x_thread" | "x_quote" | "x_reply") | null;
export type TargetPlatform1 = ("linkedin" | "x") | null;
export type HookIndex3 = number | null;
export type Posts4 = string[] | null;
export type Text10 = string | null;
export type UpdatedAt1 = string | null;
export type Cards = Card[];
export type Degraded = string | null;
export type DeliveredAt1 = string | null;
export type Id31 = string;
export type Kind4 = string | null;
export type LocalDate = string;
export type Notes2 = string[];
export type Detail = string | null;
export type Name1 = string;
export type Status3 = "ok" | "warn" | "fail" | "skip";
export type Checks = DoctorCheck[];
export type CreatedAt2 = string;
export type Id32 = string;
export type CreatedAt3 = string;
export type Hypothesis = string | null;
export type Id33 = string;
export type Instruction = string;
export type Picks = number;
export type Pillar3 = string | null;
export type Platform5 = ("linkedin" | "x") | null;
export type Status4 = "active" | "promoted" | "retired";
export type Trials = number;
export type Experiments = Experiment[];
export type AppVersion = string;
export type DisplayName = string;
export type GeneratedAt = string;
export type NextDeliveryLocal = string | null;
export type RunId = string | null;
export type SchemaVersion = number;
export type Timezone = string;
export type CapturedAt1 = string | null;
export type Comments1 = number | null;
export type CreatedAt4 = string | null;
export type ExtractionConfidence = number | null;
export type FollowersGained1 = number | null;
export type Id34 = string;
export type Impressions1 = number | null;
export type LinkClicks1 = number | null;
export type MatchConfidence = number | null;
export type Notes3 = string | null;
export type Platform6 = ("linkedin" | "x") | null;
export type PostId4 = string | null;
export type ProfileViews3 = number | null;
export type Raw = {
  [k: string]: unknown;
} | null;
export type Reactions1 = number | null;
export type Reposts1 = number | null;
export type Sends1 = number | null;
export type Source2 = "manual" | "screenshot" | "csv";
export type Status5 = "confirmed" | "needs_review" | "rejected";
export type UploadId1 = string | null;
export type Metrics = Metric[];
export type Changes = {
  [k: string]: unknown;
}[];
export type CreatedAt5 = string;
export type Experiments1 = string[];
export type Id35 = string;
export type AddedIn = string | null;
export type Confidence = "low" | "medium" | "high";
export type Evidence = string[];
export type Id36 = string;
export type Pillar4 = string | null;
export type Platform7 = ("linkedin" | "x") | null;
export type Reversal = string | null;
export type Source3 = "seed" | "reflection" | "user" | "voice";
export type Text11 = string;
export type Rules = PlaybookRule[];
export type Source4 = string | null;
export type Status6 = "active" | "retired";
export type Summary2 = string | null;
export type Version = number;
export type PlaybookHistory = Playbook1[];
export type CardId9 = string;
export type EditRatio = number | null;
export type EditingSeconds1 = number | null;
export type FinalPosts = string[];
export type FinalText = string;
export type Format2 = string | null;
export type HookUsed = {
  [k: string]: unknown;
} | null;
export type Id37 = string;
export type Pillar5 = string | null;
export type Platform8 = "linkedin" | "x";
export type PostUrl2 = string | null;
export type PostedAt2 = string;
export type Reward = number | null;
export type TimeToPostMinutes = number | null;
export type Title2 = string | null;
export type Posts5 = Post[];
export type ProcessedEventIds = string[];
export type Confidence1 = "low" | "medium" | "high";
export type CreatedAt6 = string | null;
export type DecidedAt = string | null;
export type DecisionNote = string | null;
export type Detail1 = string | null;
export type Evidence1 = string[];
export type Id38 = string;
export type Kind5 = string;
export type Source5 = string | null;
export type Status7 = "pending" | "approved" | "rejected" | "applied";
export type Title3 = string;
export type Proposals = Proposal[];
export type DailyLimit = number | null;
export type Day = string;
export type ExhaustedAt = string | null;
export type LastError1 = string | null;
export type LastErrorAt = string | null;
export type LastOkAt = string | null;
export type Model1 = string | null;
export type Provider1 = string;
export type Requests = number;
export type TokensIn = number;
export type TokensOut = number;
export type Quota = Quota1[];
export type At28 = string | null;
export type Error = string | null;
export type Id39 = string;
export type Type27 = string | null;
export type RejectedEvents = RejectedEvent[];
export type Actions = {
  [k: string]: unknown;
}[];
export type CreatedAt7 = string;
export type Id40 = string;
export type Proposals1 = string[];
export type Week1 = string;
export type ReportsIndex = {
  [k: string]: string;
}[];
export type CardIds = string[];
export type CompletedAt = string | null;
export type CreatedAt8 = string | null;
export type Error1 = string | null;
export type Id41 = string;
export type Notes4 = string | null;
export type Query2 = string;
export type Status8 = "queued" | "running" | "done" | "partial" | "failed" | "cancelled";
export type Requests1 = Request[];
export type Degraded1 = string | null;
export type EndedAt = string | null;
export type At29 = string | null;
export type Message = string | null;
export type Type28 = string;
export type Where = string;
export type Errors = RunError[];
export type Id42 = string;
export type Notes5 = string[];
export type StartedAt = string;
export type Status9 = "running" | "ok" | "partial" | "failed";
export type Steps = {
  [k: string]: unknown;
}[];
export type Task = string;
export type Trigger = string | null;
export type Runs = Run[];
export type Active1 = boolean;
export type AddedBy = string | null;
export type BestEffort = boolean;
export type ConsecutiveFailures = number;
export type ItemsLastRun = number | null;
export type ItemsTotal = number | null;
export type LastError2 = string | null;
export type LastFetchAt = string | null;
export type LastSuccessAt = string | null;
export type Id43 = string;
export type Kind6 = string;
export type Lang2 = string;
export type Name2 = string;
export type PausedReason = string | null;
export type Query3 = string | null;
export type Scout1 = string;
export type Tier3 = string | null;
export type Url2 = string | null;
export type Sources1 = Source6[];
export type CustomText1 = string | null;
export type PositionKey = string | null;
export type Context2 = string | null;
export type CreatedBy = string | null;
export type Id44 = string;
export type Issue2 = string;
export type Keywords1 = string[];
export type Key1 = string;
export type Label1 = string;
export type Text12 = string;
export type Positions1 = Position[];
export type Sources2 = SourceRef[];
export type Status10 = "proposed" | "active" | "archived";
export type Tier4 = "world" | "india" | "bihar" | "other";
export type UpdatedAt2 = string | null;
export type Stances = Stance[];
export type CreatedAt9 = string | null;
export type Error2 = string | null;
export type Id45 = string;
export type Note6 = string | null;
export type Paths1 = string[];
export type ProcessedAt = string | null;
export type Results = {
  [k: string]: unknown;
} | null;
export type Status11 = "pending" | "processed" | "failed";
export type Week2 = string | null;
export type Uploads = MetricUpload[];
export type AddedPhrases = {
  [k: string]: unknown;
}[];
export type Avoid = string[];
export type CreatedAt10 = string;
export type CutPhrases = {
  [k: string]: unknown;
}[];
export type Id46 = string;
export type Rules1 = string[];
export type Summary3 = string | null;
export type Version1 = number;
export type At30 = string | null;
export type Code = string;
export type Level = "info" | "warn" | "error";
export type Message1 = string;
export type Warnings = DeskWarning[];

export interface Contracts {
  batch: InboxBatch;
  desk: DeskState;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "InboxBatch".
 */
export interface InboxBatch {
  created_at: CreatedAt;
  device?: Device;
  events: Events;
  id: Id26;
  v?: V;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "CardStatusEvent".
 */
export interface CardStatusEvent {
  at: At;
  card_id: CardId;
  id: Id;
  status: Status;
  type: Type;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "CardEditEvent".
 */
export interface CardEditEvent {
  at: At1;
  card_id: CardId1;
  hook_index?: HookIndex;
  id: Id1;
  posts?: Posts;
  text?: Text;
  type: Type1;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "CardPostedEvent".
 */
export interface CardPostedEvent {
  at: At2;
  card_id: CardId2;
  editing_seconds?: EditingSeconds;
  hook_index?: HookIndex1;
  id: Id2;
  post_url?: PostUrl;
  posted_at?: PostedAt;
  posts?: Posts1;
  text?: Text1;
  type: Type2;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "CardSkipEvent".
 */
export interface CardSkipEvent {
  at: At3;
  card_id: CardId3;
  id: Id3;
  note?: Note;
  reason: Reason;
  type: Type3;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "CardRewriteEvent".
 */
export interface CardRewriteEvent {
  at: At4;
  card_id: CardId4;
  chips?: Chips;
  id: Id4;
  note?: Note1;
  target_format?: TargetFormat;
  target_platform?: TargetPlatform;
  type: Type4;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "CardAnswersEvent".
 */
export interface CardAnswersEvent {
  answers: Answers;
  at: At5;
  card_id: CardId5;
  id: Id5;
  reusable?: Reusable;
  save_as_stance?: StanceFromAnswer | null;
  type: Type5;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "AnswerIn".
 */
export interface AnswerIn {
  answer: Answer;
  question_id: QuestionId;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "StanceFromAnswer".
 */
export interface StanceFromAnswer {
  issue?: Issue;
  stance_id?: StanceId;
  text: Text2;
  tier?: Tier;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "CardRestoreEvent".
 */
export interface CardRestoreEvent {
  at: At6;
  card_id: CardId6;
  id: Id6;
  type: Type6;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "CardDraftNowEvent".
 */
export interface CardDraftNowEvent {
  at: At7;
  card_id: CardId7;
  id: Id7;
  type: Type7;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "CardHookEvent".
 */
export interface CardHookEvent {
  at: At8;
  card_id: CardId8;
  hook_index: HookIndex2;
  id: Id8;
  type: Type8;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PostUpdateEvent".
 */
export interface PostUpdateEvent {
  at: At9;
  id: Id9;
  post_id: PostId;
  post_url?: PostUrl1;
  posted_at?: PostedAt1;
  posts?: Posts2;
  text?: Text3;
  type: Type9;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PostMetricsEvent".
 */
export interface PostMetricsEvent {
  at: At10;
  captured_at?: CapturedAt;
  id: Id10;
  post_id: PostId1;
  type: Type10;
  values: MetricValues;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "MetricValues".
 */
export interface MetricValues {
  comments?: Comments;
  followers_gained?: FollowersGained;
  impressions?: Impressions;
  link_clicks?: LinkClicks;
  profile_views?: ProfileViews;
  reactions?: Reactions;
  reposts?: Reposts;
  sends?: Sends;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "MetricsUploadEvent".
 */
export interface MetricsUploadEvent {
  at: At11;
  id: Id11;
  note?: Note2;
  paths: Paths;
  type: Type11;
  upload_id: UploadId;
  week?: Week;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "MetricsReviewEvent".
 */
export interface MetricsReviewEvent {
  action: Action;
  at: At12;
  id: Id12;
  metric_id: MetricId;
  post_id?: PostId2;
  type: Type12;
  values?: MetricValues | null;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "AccountStatsEvent".
 */
export interface AccountStatsEvent {
  at: At13;
  date: Date;
  followers?: Followers;
  id: Id13;
  platform: Platform;
  profile_views?: ProfileViews1;
  type: Type13;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "RequestCreateEvent".
 */
export interface RequestCreateEvent {
  at: At14;
  id: Id14;
  notes?: Notes;
  platforms: Platforms;
  query: Query;
  request_id: RequestId;
  type: Type14;
}
export interface Platforms {
  [k: string]: number;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "RequestCancelEvent".
 */
export interface RequestCancelEvent {
  at: At15;
  id: Id15;
  request_id: RequestId1;
  type: Type15;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "StanceUpsertEvent".
 */
export interface StanceUpsertEvent {
  at: At16;
  chosen_key?: ChosenKey;
  clear_choice?: ClearChoice;
  context?: Context;
  custom_text?: CustomText;
  id: Id16;
  issue?: Issue1;
  keywords?: Keywords;
  positions?: Positions;
  stance_id: StanceId1;
  status?: Status1;
  tier?: Tier1;
  type: Type16;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PositionIn".
 */
export interface PositionIn {
  key: Key;
  label: Label;
  text: Text4;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "StanceDeleteEvent".
 */
export interface StanceDeleteEvent {
  at: At17;
  id: Id17;
  stance_id: StanceId2;
  type: Type17;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "StanceProposeEvent".
 */
export interface StanceProposeEvent {
  at: At18;
  count?: Count;
  id: Id18;
  type: Type18;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "SourceUpsertEvent".
 */
export interface SourceUpsertEvent {
  active?: Active;
  at: At19;
  id: Id19;
  kind?: Kind;
  lang?: Lang;
  name?: Name;
  pillar_hints?: PillarHints;
  query?: Query1;
  scout?: Scout;
  source_id: SourceId;
  tier?: Tier2;
  type: Type19;
  url?: Url;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "SourceDeleteEvent".
 */
export interface SourceDeleteEvent {
  at: At20;
  id: Id20;
  source_id: SourceId1;
  type: Type20;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "SettingsUpdateEvent".
 */
export interface SettingsUpdateEvent {
  at: At21;
  id: Id21;
  patch: Patch;
  type: Type21;
}
export interface Patch {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "ProfileUpdateEvent".
 */
export interface ProfileUpdateEvent {
  at: At22;
  id: Id22;
  text: Text5;
  type: Type22;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "ProposalDecideEvent".
 */
export interface ProposalDecideEvent {
  at: At23;
  decision: Decision;
  id: Id23;
  note?: Note3;
  proposal_id: ProposalId;
  type: Type23;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlaybookRuleEvent".
 */
export interface PlaybookRuleEvent {
  action: Action1;
  at: At24;
  id: Id24;
  pillar?: Pillar;
  platform?: Platform1;
  rule_id?: RuleId;
  text?: Text6;
  type: Type24;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "RunRequestEvent".
 */
export interface RunRequestEvent {
  at: At25;
  force?: Force;
  id: Id25;
  tasks?: Tasks;
  type: Type25;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "DeskState".
 */
export interface DeskState {
  account_stats?: AccountStats;
  archive_months?: ArchiveMonths;
  arms?: Arms;
  cards?: Cards;
  delivery?: DeliveryInfo | null;
  doctor?: DoctorReport | null;
  experiments?: Experiments;
  meta: DeskMeta;
  metrics?: Metrics;
  playbook?: Playbook1 | null;
  playbook_history?: PlaybookHistory;
  posts?: Posts5;
  processed_event_ids?: ProcessedEventIds;
  proposals?: Proposals;
  quota?: Quota;
  rejected_events?: RejectedEvents;
  report?: SystemReport | null;
  reports_index?: ReportsIndex;
  requests?: Requests1;
  runs?: Runs;
  settings: Settings;
  settings_overrides?: SettingsOverrides;
  sources?: Sources1;
  stances?: Stances;
  stats?: Stats1;
  uploads?: Uploads;
  voice?: VoiceProfile | null;
  warnings?: Warnings;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "AccountStat".
 */
export interface AccountStat {
  date: Date1;
  followers?: Followers1;
  id: Id27;
  platform: Platform2;
  profile_views?: ProfileViews2;
  source?: Source;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Arm".
 */
export interface Arm {
  alpha: Alpha;
  beta: Beta;
  format: Format;
  id: Id28;
  mean: Mean;
  n_obs: NObs;
  pillar: Pillar1;
  platform: Platform3;
  prior_mean: PriorMean;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Card".
 */
export interface Card {
  affairs_type?: AffairsType;
  angle?: Angle;
  answers?: Answers1;
  arm?: Arm1;
  claims?: Claims;
  created_at: CreatedAt1;
  delivered_at?: DeliveredAt;
  delivery_id?: DeliveryId;
  draft?: Draft | null;
  draft_original?: Draft | null;
  draft_state?: DraftState;
  experiment_id?: ExperimentId;
  expires_at?: ExpiresAt;
  explore?: Explore;
  flags?: Flags;
  format: Format1;
  format_note?: FormatNote;
  hook_type?: HookType;
  hooks?: Hooks;
  id: Id29;
  issue_key?: IssueKey;
  kind?: Kind1;
  llm?: LLMInfo | null;
  mode?: Mode;
  pillar: Pillar2;
  platform: Platform4;
  post_id?: PostId3;
  questions?: Questions;
  rank?: Rank;
  request_id?: RequestId2;
  revision?: Revision;
  rewrite_count?: RewriteCount;
  score?: Score;
  score_parts?: ScoreParts;
  skip?: Skip | null;
  sources?: Sources;
  status: Status2;
  status_changed_at?: StatusChangedAt;
  title: Title1;
  topic_id?: TopicId;
  updated_at?: UpdatedAt;
  versions?: Versions;
  why_now?: WhyNow;
  work?: Work | null;
  working?: Working | null;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Answer".
 */
export interface Answer1 {
  answer: Answer2;
  at?: At26;
  question_id: QuestionId1;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Claim".
 */
export interface Claim {
  source?: Source1;
  text: Text7;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Draft".
 */
export interface Draft {
  posts?: Posts3;
  quote_url?: QuoteUrl;
  reply?: ReplyTarget | null;
  text?: Text8;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "ReplyTarget".
 */
export interface ReplyTarget {
  accounts?: Accounts;
  context?: Context1;
  search_terms?: SearchTerms;
}
export interface Flags {
  avoid_phrases?: AvoidPhrases;
  bait?: Bait;
  blocked?: Blocked;
  first_person?: FirstPerson;
  length?: Length;
  notes?: Notes1;
  opinion?: Opinion;
  sensitive?: Sensitive;
  sensitive_reason?: SensitiveReason;
  stance_id?: StanceId3;
  unsourced?: Unsourced;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Hook".
 */
export interface Hook {
  text: Text9;
  type?: Type26;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "LLMInfo".
 */
export interface LLMInfo {
  model?: Model;
  provider?: Provider;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Question".
 */
export interface Question {
  id: Id30;
  kind?: Kind2;
  q: Q;
  why?: Why;
}
export interface ScoreParts {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Skip".
 */
export interface Skip {
  at?: At27;
  note?: Note4;
  reason: Reason1;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "SourceRef".
 */
export interface SourceRef {
  lang?: Lang1;
  orig_title?: OrigTitle;
  published_at?: PublishedAt;
  publisher?: Publisher;
  summary?: Summary;
  title?: Title;
  url: Url1;
}
export interface Versions {
  playbook?: Playbook;
  prompt?: Prompt;
  voice?: Voice;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Work".
 */
export interface Work {
  attempts?: Attempts;
  chips?: Chips1;
  kind: Kind3;
  last_error?: LastError;
  note?: Note5;
  requested_at?: RequestedAt;
  target_format?: TargetFormat1;
  target_platform?: TargetPlatform1;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Working".
 */
export interface Working {
  hook_index?: HookIndex3;
  posts?: Posts4;
  text?: Text10;
  updated_at?: UpdatedAt1;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "DeliveryInfo".
 */
export interface DeliveryInfo {
  counts?: Counts;
  degraded?: Degraded;
  delivered_at?: DeliveredAt1;
  id: Id31;
  kind?: Kind4;
  local_date: LocalDate;
  notes?: Notes2;
}
export interface Counts {
  [k: string]: number;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "DoctorReport".
 */
export interface DoctorReport {
  checks?: Checks;
  created_at: CreatedAt2;
  id: Id32;
  summary?: Summary1;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "DoctorCheck".
 */
export interface DoctorCheck {
  detail?: Detail;
  name: Name1;
  status: Status3;
}
export interface Summary1 {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Experiment".
 */
export interface Experiment {
  created_at: CreatedAt3;
  hypothesis?: Hypothesis;
  id: Id33;
  instruction: Instruction;
  picks?: Picks;
  pillar?: Pillar3;
  platform?: Platform5;
  stats?: Stats;
  status?: Status4;
  trials?: Trials;
}
export interface Stats {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "DeskMeta".
 */
export interface DeskMeta {
  app_version: AppVersion;
  display_name: DisplayName;
  generated_at: GeneratedAt;
  next_delivery_local?: NextDeliveryLocal;
  run_id?: RunId;
  schema_version?: SchemaVersion;
  timezone: Timezone;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Metric".
 */
export interface Metric {
  captured_at?: CapturedAt1;
  comments?: Comments1;
  created_at?: CreatedAt4;
  extraction_confidence?: ExtractionConfidence;
  followers_gained?: FollowersGained1;
  id: Id34;
  impressions?: Impressions1;
  link_clicks?: LinkClicks1;
  match_confidence?: MatchConfidence;
  notes?: Notes3;
  platform?: Platform6;
  post_id?: PostId4;
  profile_views?: ProfileViews3;
  raw?: Raw;
  reactions?: Reactions1;
  reposts?: Reposts1;
  sends?: Sends1;
  source?: Source2;
  status?: Status5;
  upload_id?: UploadId1;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Playbook".
 */
export interface Playbook1 {
  changes?: Changes;
  created_at: CreatedAt5;
  experiments?: Experiments1;
  id: Id35;
  rules?: Rules;
  source?: Source4;
  status?: Status6;
  summary?: Summary2;
  version: Version;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "PlaybookRule".
 */
export interface PlaybookRule {
  added_in?: AddedIn;
  confidence?: Confidence;
  evidence?: Evidence;
  id: Id36;
  pillar?: Pillar4;
  platform?: Platform7;
  reversal?: Reversal;
  source?: Source3;
  text: Text11;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Post".
 */
export interface Post {
  card_id: CardId9;
  edit_ratio?: EditRatio;
  edit_stats?: EditStats;
  editing_seconds?: EditingSeconds1;
  features?: Features;
  final_posts?: FinalPosts;
  final_text?: FinalText;
  format?: Format2;
  guard?: Guard;
  hook_used?: HookUsed;
  id: Id37;
  latest_metrics?: Metric | null;
  pillar?: Pillar5;
  platform: Platform8;
  post_url?: PostUrl2;
  posted_at: PostedAt2;
  reward?: Reward;
  reward_parts?: RewardParts;
  time_to_post_minutes?: TimeToPostMinutes;
  title?: Title2;
}
export interface EditStats {
  [k: string]: unknown;
}
export interface Features {
  [k: string]: unknown;
}
export interface Guard {
  [k: string]: unknown;
}
export interface RewardParts {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Proposal".
 */
export interface Proposal {
  confidence?: Confidence1;
  created_at?: CreatedAt6;
  decided_at?: DecidedAt;
  decision_note?: DecisionNote;
  detail?: Detail1;
  evidence?: Evidence1;
  id: Id38;
  kind: Kind5;
  payload?: Payload;
  source?: Source5;
  status?: Status7;
  title: Title3;
}
export interface Payload {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Quota".
 */
export interface Quota1 {
  daily_limit?: DailyLimit;
  day: Day;
  exhausted_at?: ExhaustedAt;
  last_error?: LastError1;
  last_error_at?: LastErrorAt;
  last_ok_at?: LastOkAt;
  model?: Model1;
  provider: Provider1;
  requests?: Requests;
  tokens_in?: TokensIn;
  tokens_out?: TokensOut;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "RejectedEvent".
 */
export interface RejectedEvent {
  at?: At28;
  error?: Error;
  id: Id39;
  type?: Type27;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "SystemReport".
 */
export interface SystemReport {
  actions?: Actions;
  created_at: CreatedAt7;
  id: Id40;
  period?: Period;
  proposals?: Proposals1;
  sections?: Sections;
  week: Week1;
}
export interface Period {
  [k: string]: unknown;
}
export interface Sections {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Request".
 */
export interface Request {
  card_ids?: CardIds;
  completed_at?: CompletedAt;
  created_at?: CreatedAt8;
  error?: Error1;
  id: Id41;
  notes?: Notes4;
  platforms?: Platforms1;
  query: Query2;
  status?: Status8;
}
export interface Platforms1 {
  [k: string]: number;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Run".
 */
export interface Run {
  degraded?: Degraded1;
  ended_at?: EndedAt;
  errors?: Errors;
  id: Id42;
  llm?: Llm;
  notes?: Notes5;
  started_at: StartedAt;
  status?: Status9;
  steps?: Steps;
  task: Task;
  trigger?: Trigger;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "RunError".
 */
export interface RunError {
  at?: At29;
  message?: Message;
  type: Type28;
  where: Where;
}
export interface Llm {
  [k: string]: unknown;
}
export interface Settings {
  [k: string]: unknown;
}
export interface SettingsOverrides {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Source".
 */
export interface Source6 {
  active?: Active1;
  added_by?: AddedBy;
  best_effort?: BestEffort;
  health?: SourceHealth;
  id: Id43;
  kind: Kind6;
  lang?: Lang2;
  name: Name2;
  paused_reason?: PausedReason;
  query?: Query3;
  scout: Scout1;
  tier?: Tier3;
  url?: Url2;
  yield_stats?: YieldStats;
}
export interface SourceHealth {
  consecutive_failures?: ConsecutiveFailures;
  items_last_run?: ItemsLastRun;
  items_total?: ItemsTotal;
  last_error?: LastError2;
  last_fetch_at?: LastFetchAt;
  last_success_at?: LastSuccessAt;
}
export interface YieldStats {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Stance".
 */
export interface Stance {
  chosen?: StanceChoice | null;
  context?: Context2;
  created_by?: CreatedBy;
  id: Id44;
  issue: Issue2;
  keywords?: Keywords1;
  positions?: Positions1;
  sources?: Sources2;
  status?: Status10;
  tier?: Tier4;
  updated_at?: UpdatedAt2;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "StanceChoice".
 */
export interface StanceChoice {
  custom_text?: CustomText1;
  position_key?: PositionKey;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Position".
 */
export interface Position {
  key: Key1;
  label: Label1;
  text: Text12;
}
export interface Stats1 {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "MetricUpload".
 */
export interface MetricUpload {
  created_at?: CreatedAt9;
  error?: Error2;
  id: Id45;
  note?: Note6;
  paths?: Paths1;
  processed_at?: ProcessedAt;
  results?: Results;
  status?: Status11;
  week?: Week2;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "VoiceProfile".
 */
export interface VoiceProfile {
  added_phrases?: AddedPhrases;
  avoid?: Avoid;
  created_at: CreatedAt10;
  cut_phrases?: CutPhrases;
  examples?: Examples;
  id: Id46;
  rules?: Rules1;
  stats?: Stats2;
  summary?: Summary3;
  version: Version1;
}
export interface Examples {
  [k: string]: string[];
}
export interface Stats2 {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "DeskWarning".
 */
export interface DeskWarning {
  at?: At30;
  code: Code;
  level?: Level;
  message: Message1;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Flags".
 */
export interface Flags1 {
  avoid_phrases?: AvoidPhrases;
  bait?: Bait;
  blocked?: Blocked;
  first_person?: FirstPerson;
  length?: Length;
  notes?: Notes1;
  opinion?: Opinion;
  sensitive?: Sensitive;
  sensitive_reason?: SensitiveReason;
  stance_id?: StanceId3;
  unsourced?: Unsourced;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "SourceHealth".
 */
export interface SourceHealth1 {
  consecutive_failures?: ConsecutiveFailures;
  items_last_run?: ItemsLastRun;
  items_total?: ItemsTotal;
  last_error?: LastError2;
  last_fetch_at?: LastFetchAt;
  last_success_at?: LastSuccessAt;
}
/**
 * This interface was referenced by `Contracts`'s JSON-Schema
 * via the `definition` "Versions".
 */
export interface Versions1 {
  playbook?: Playbook;
  prompt?: Prompt;
  voice?: Voice;
}

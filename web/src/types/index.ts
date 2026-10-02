// Friendly names over the generated contract (contracts.ts is generated from pbs/contracts.py).
// Derived structurally from DeskState and InboxBatch so they don't depend on generated interface names.
import type * as C from "./contracts";

type Item<T> = NonNullable<T> extends Array<infer U> ? U : never;

export type DeskState = C.DeskState;
export type InboxBatch = C.InboxBatch;
export type InboxEvent = InboxBatch["events"][number];

export type Card = Item<DeskState["cards"]>;
export type Draft = NonNullable<Card["draft"]>;
export type Hook = Item<Card["hooks"]>;
export type SourceRef = Item<Card["sources"]>;
export type Flags = NonNullable<Card["flags"]>;
export type EditInfo = NonNullable<NonNullable<Card["llm"]>["edit"]>;
export type Visual = NonNullable<Card["visual"]>;
export type VisualItem = Item<Visual["items"]>;
export type Question = Item<Card["questions"]>;
export type Post = Item<DeskState["posts"]>;
export type Metric = Item<DeskState["metrics"]>;
export type MetricUpload = Item<DeskState["uploads"]>;
export type AccountStat = Item<DeskState["account_stats"]>;
export type Stance = Item<DeskState["stances"]>;
export type Position = Item<Stance["positions"]>;
export type RequestRow = Item<DeskState["requests"]>;
export type Source = Item<DeskState["sources"]>;
export type Proposal = Item<DeskState["proposals"]>;
export type Playbook = NonNullable<DeskState["playbook"]>;
export type PlaybookRule = Item<Playbook["rules"]>;
export type Experiment = Item<DeskState["experiments"]>;
export type SystemReport = NonNullable<DeskState["report"]>;
export type VoiceProfile = NonNullable<DeskState["voice"]>;
export type Arm = Item<DeskState["arms"]>;
export type Run = Item<DeskState["runs"]>;
export type Quota = Item<DeskState["quota"]>;
export type DeskWarning = Item<DeskState["warnings"]>;
export type DeliveryInfo = NonNullable<DeskState["delivery"]>;
export type RejectedEvent = Item<DeskState["rejected_events"]>;
export type DoctorReport = NonNullable<DeskState["doctor"]>;
export type ImagesStatus = NonNullable<DeskState["images"]>;

export type Platform = Card["platform"];
export type CardStatus = Card["status"];
export type FormatName = Card["format"];
export type SkipReason = Extract<InboxEvent, { type: "card.skip" }>["reason"];
export type MetricValues = Extract<InboxEvent, { type: "post.metrics" }>["values"];

/** Event payload without the envelope fields the outbox fills in. */
export type EventInput = InboxEvent extends infer E ? (E extends InboxEvent ? Omit<E, "id" | "at"> : never) : never;

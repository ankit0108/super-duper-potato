// Applies events that haven't been processed by the pipeline yet to the last desk.json, so every action
// shows up instantly (and offline). Pure: returns a new state plus the ids that are still pending.
import type { Card, DeskState, InboxEvent, Post, Stance } from "@/types";
import { draftText } from "./format";
import { withoutHashtags } from "./hashtags";
import { editRatio } from "./text";

export type Pending = {
  cards: Set<string>;
  posts: Set<string>;
  requests: Set<string>;
  stances: Set<string>;
  sources: Set<string>;
  proposals: Set<string>;
  metrics: Set<string>;
  settings: boolean;
  profile: boolean;
  runRequested: string[];
};

export const emptyPending = (): Pending => ({
  cards: new Set(),
  posts: new Set(),
  requests: new Set(),
  stances: new Set(),
  sources: new Set(),
  proposals: new Set(),
  metrics: new Set(),
  settings: false,
  profile: false,
  runRequested: [],
});

type AnyObj = Record<string, unknown>;

export function deepMerge<T extends AnyObj>(base: T, patch: AnyObj): T {
  const out: AnyObj = { ...base };
  for (const [k, v] of Object.entries(patch)) {
    if (v === null) delete out[k];
    else if (v && typeof v === "object" && !Array.isArray(v) && out[k] && typeof out[k] === "object" && !Array.isArray(out[k]))
      out[k] = deepMerge(out[k] as AnyObj, v as AnyObj);
    else out[k] = v;
  }
  return out as T;
}

export function applyEvents(desk: DeskState, events: InboxEvent[]): { desk: DeskState; pending: Pending } {
  const pending = emptyPending();
  if (!events.length) return { desk, pending };
  const out: DeskState = {
    ...desk,
    cards: [...(desk.cards ?? [])],
    posts: [...(desk.posts ?? [])],
    requests: [...(desk.requests ?? [])],
    stances: [...(desk.stances ?? [])],
    sources: [...(desk.sources ?? [])],
    proposals: [...(desk.proposals ?? [])],
    metrics: [...(desk.metrics ?? [])],
    uploads: [...(desk.uploads ?? [])],
    account_stats: [...(desk.account_stats ?? [])],
  };
  const cardIndex = new Map(out.cards!.map((c, i) => [c.id, i]));
  const updateCard = (id: string, fn: (c: Card) => Card) => {
    const i = cardIndex.get(id);
    if (i == null) return;
    out.cards![i] = fn({ ...out.cards![i] });
    pending.cards.add(id);
  };
  const updateStance = (id: string, fn: (s: Stance) => Stance | null) => {
    const i = out.stances!.findIndex((s) => s.id === id);
    const next = fn(i >= 0 ? { ...out.stances![i] } : ({ id, issue: "", tier: "other" } as Stance));
    if (next == null) return;
    if (i >= 0) out.stances![i] = next;
    else out.stances!.push(next);
    pending.stances.add(id);
  };

  for (const ev of events) {
    switch (ev.type) {
      case "card.status":
        updateCard(ev.card_id, (c) => ({ ...c, status: ev.status, status_changed_at: ev.at }));
        break;
      case "card.edit":
        updateCard(ev.card_id, (c) => ({
          ...c,
          working: {
            text: ev.text ?? null,
            posts: ev.posts ?? null,
            hook_index: ev.hook_index ?? null,
            hooks: ev.hooks ?? c.working?.hooks ?? null,
            hashtags: ev.hashtags ?? c.working?.hashtags ?? null,
            // His wording of the current visual (it belongs to that visual: a newer one replaces it).
            visual: ev.visual
              ? { ...ev.visual, sources: c.visual?.sources ?? [], unsourced: c.visual?.unsourced ?? [], created_at: c.visual?.created_at ?? null }
              : (c.working?.visual ?? null),
            updated_at: ev.at,
          },
          status: c.status === "suggested" || c.status === "blocked" ? "editing" : c.status,
        }));
        break;
      case "card.posted": {
        const i = cardIndex.get(ev.card_id);
        if (i == null) break;
        const card = out.cards![i];
        const finalPosts = ev.posts ?? card.working?.posts ?? card.draft?.posts ?? [];
        const finalText =
          card.format === "x_thread" && finalPosts.length ? finalPosts.join("\n\n") : (ev.text ?? card.working?.text ?? card.draft?.text ?? "");
        const base = draftText(card);
        const postId = `pending_${ev.id}`;
        const post: Post = {
          id: postId,
          card_id: card.id,
          platform: card.platform,
          pillar: card.pillar,
          format: card.format,
          title: card.title,
          final_text: finalText,
          final_posts: card.format === "x_thread" ? finalPosts : [],
          hashtags: ev.hashtags ?? [],
          posted_at: ev.posted_at ?? ev.at,
          post_url: ev.post_url ?? null,
          edit_ratio: base ? editRatio(base, withoutHashtags(finalText, ev.hashtags ?? [])) : null,
          editing_seconds: ev.editing_seconds ?? null,
        };
        out.posts = [post, ...out.posts!.filter((p) => p.card_id !== card.id)];
        pending.posts.add(postId);
        updateCard(card.id, (c) => ({ ...c, status: "posted", post_id: postId, status_changed_at: ev.posted_at ?? ev.at }));
        break;
      }
      case "card.skip":
        updateCard(ev.card_id, (c) => ({
          ...c,
          status: "skipped",
          skip: { reason: ev.reason, note: ev.note ?? null, at: ev.at },
          status_changed_at: ev.at,
          work: null,
        }));
        break;
      case "card.rewrite":
        updateCard(ev.card_id, (c) => ({
          ...c,
          work: {
            kind: "rewrite",
            note: ev.note,
            chips: ev.chips ?? [],
            requested_at: ev.at,
            target_platform: ev.target_platform ?? null,
            target_format: ev.target_format ?? null,
          },
        }));
        break;
      case "card.crosspost": {
        // A version for the other platform is on its way; "switch" also skips this one (right topic, wrong platform).
        const i = cardIndex.get(ev.card_id);
        if (i == null || out.cards![i].platform === ev.target_platform) break;
        const mode = out.cards![i].status === "posted" ? "both" : (ev.mode ?? "both");
        updateCard(ev.card_id, (c) => ({
          ...c,
          work: {
            kind: "rewrite",
            note: ev.note ?? "",
            chips: [],
            requested_at: ev.at,
            target_platform: ev.target_platform,
            target_format: ev.target_format ?? null,
            crosspost: mode,
          },
          ...(mode === "switch"
            ? { status: "skipped" as const, skip: { reason: "wrong_platform" as const, note: ev.note?.trim() || null, at: ev.at }, status_changed_at: ev.at }
            : {}),
        }));
        break;
      }
      case "card.visual":
        updateCard(ev.card_id, (c) => ({ ...c, work: { kind: "visual", visual_kind: ev.kind ?? "auto", note: ev.note ?? "", requested_at: ev.at } }));
        break;
      case "card.answers":
        updateCard(ev.card_id, (c) => {
          const answers = new Map((c.answers ?? []).map((a) => [a.question_id, a]));
          for (const a of ev.answers) answers.set(a.question_id, { question_id: a.question_id, answer: a.answer, at: ev.at });
          return { ...c, answers: [...answers.values()], work: { kind: "draft", requested_at: ev.at } };
        });
        break;
      case "card.restore":
        updateCard(ev.card_id, (c) => ({
          ...c,
          status: c.mode === "interview" && !c.draft ? "needs_input" : "editing",
          skip: null,
          status_changed_at: ev.at,
        }));
        break;
      case "card.draft_now":
        updateCard(ev.card_id, (c) => ({ ...c, work: { kind: "draft", requested_at: ev.at } }));
        break;
      case "card.hook":
        break;
      case "post.update":
        out.posts = out.posts!.map((p) =>
          p.id === ev.post_id
            ? {
                ...p,
                post_url: ev.post_url ?? p.post_url,
                posted_at: ev.posted_at ?? p.posted_at,
                final_text: ev.posts?.length ? ev.posts.join("\n\n") : (ev.text ?? p.final_text),
                final_posts: ev.posts ?? p.final_posts,
              }
            : p,
        );
        pending.posts.add(ev.post_id);
        break;
      case "post.metrics":
        out.posts = out.posts!.map((p) =>
          p.id === ev.post_id
            ? {
                ...p,
                latest_metrics: {
                  id: `pending_${ev.id}`,
                  post_id: p.id,
                  platform: p.platform,
                  captured_at: ev.captured_at ?? ev.at,
                  source: "manual",
                  status: "confirmed",
                  ...ev.values,
                },
              }
            : p,
        );
        pending.posts.add(ev.post_id);
        break;
      case "metrics.upload":
        out.uploads = [
          { id: ev.upload_id, paths: ev.paths, week: ev.week ?? null, note: ev.note ?? null, status: "pending", created_at: ev.at },
          ...out.uploads!.filter((u) => u.id !== ev.upload_id),
        ];
        break;
      case "metrics.review":
        out.metrics = out.metrics!.map((m) =>
          m.id === ev.metric_id
            ? {
                ...m,
                status: ev.action === "reject" ? "rejected" : "confirmed",
                post_id: ev.post_id ?? m.post_id,
                ...(ev.action === "edit" && ev.values ? ev.values : {}),
              }
            : m,
        );
        pending.metrics.add(ev.metric_id);
        break;
      case "account.stats":
        out.account_stats = [
          { id: `acs_${ev.platform}_${ev.date}`, date: ev.date, platform: ev.platform, followers: ev.followers ?? null, profile_views: ev.profile_views ?? null, source: "manual" },
          ...out.account_stats!.filter((a) => a.id !== `acs_${ev.platform}_${ev.date}`),
        ];
        break;
      case "request.create":
        if (!out.requests!.some((r) => r.id === ev.request_id)) {
          out.requests = [
            { id: ev.request_id, query: ev.query, platforms: ev.platforms as Record<string, number>, notes: ev.notes ?? null, status: "queued", created_at: ev.at, card_ids: [] },
            ...out.requests!,
          ];
        }
        pending.requests.add(ev.request_id);
        break;
      case "request.cancel":
        out.requests = out.requests!.map((r) => (r.id === ev.request_id ? { ...r, status: "cancelled" } : r));
        pending.requests.add(ev.request_id);
        break;
      case "stance.upsert":
        updateStance(ev.stance_id, (s) => {
          const next: Stance = { ...s, updated_at: ev.at };
          if (ev.issue != null) next.issue = ev.issue;
          if (ev.tier != null) next.tier = ev.tier;
          if (ev.context != null) next.context = ev.context;
          if (ev.positions != null) next.positions = ev.positions;
          if (ev.keywords != null) next.keywords = ev.keywords;
          if (ev.status != null) next.status = ev.status;
          if (ev.clear_choice) next.chosen = null;
          else if (ev.chosen_key != null || ev.custom_text != null) {
            next.chosen = { position_key: ev.chosen_key || null, custom_text: ev.custom_text?.trim() || null };
            if (next.status === "proposed" || !next.status) next.status = "active";
          }
          return next;
        });
        break;
      case "stance.delete":
        updateStance(ev.stance_id, (s) => ({ ...s, status: "archived" }));
        break;
      case "stance.propose":
        pending.runRequested.push("stances");
        break;
      case "source.upsert": {
        const i = out.sources!.findIndex((s) => s.id === ev.source_id);
        const base =
          i >= 0
            ? out.sources![i]
            : { id: ev.source_id, name: ev.name ?? ev.source_id, kind: ev.kind ?? "rss", scout: ev.scout ?? "tech", added_by: "user", active: true, lang: "en" };
        const next = {
          ...base,
          ...Object.fromEntries(Object.entries({ name: ev.name, kind: ev.kind, url: ev.url, query: ev.query, scout: ev.scout, tier: ev.tier, lang: ev.lang, active: ev.active }).filter(([, v]) => v != null)),
        };
        if (i >= 0) out.sources![i] = next as typeof base;
        else out.sources!.push(next as typeof base);
        pending.sources.add(ev.source_id);
        break;
      }
      case "source.delete":
        out.sources = out.sources!.filter((s) => s.id !== ev.source_id);
        break;
      case "settings.update":
        out.settings_overrides = deepMerge((out.settings_overrides ?? {}) as AnyObj, ev.patch as AnyObj);
        out.settings = deepMerge(out.settings as AnyObj, ev.patch as AnyObj);
        pending.settings = true;
        break;
      case "profile.update":
        out.settings = { ...out.settings, profile: ev.text };
        pending.profile = true;
        break;
      case "proposal.decide":
        out.proposals = out.proposals!.map((p) =>
          p.id === ev.proposal_id ? { ...p, status: ev.decision === "approve" ? "approved" : "rejected", decided_at: ev.at } : p,
        );
        pending.proposals.add(ev.proposal_id);
        break;
      case "playbook.rule":
        if (out.playbook) {
          let rules = [...(out.playbook.rules ?? [])];
          if (ev.action === "add" && ev.text) rules.push({ id: `pending_${ev.id}`, text: ev.text, platform: ev.platform ?? null, pillar: ev.pillar ?? null, source: "user", confidence: "high" });
          if (ev.action === "remove") rules = rules.filter((r) => r.id !== ev.rule_id);
          if (ev.action === "edit") rules = rules.map((r) => (r.id === ev.rule_id && ev.text ? { ...r, text: ev.text, source: "user" } : r));
          out.playbook = { ...out.playbook, rules };
        }
        break;
      case "run.request":
        pending.runRequested.push(...(ev.tasks?.length ? ev.tasks : ["tick"]));
        break;
    }
  }
  return { desk: out, pending };
}

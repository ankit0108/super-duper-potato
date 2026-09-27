import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, Download, LogOut, Save } from "lucide-react";
import type { Platform } from "@/types";
import { parseTerms } from "@/lib/guard";
import { navigate } from "@/lib/router";
import { keysWithPrefix, remove } from "@/lib/storage";
import { useDesk } from "@/state/store";
import { Badge } from "@/components/ui/Badge";
import { Button, IconButton } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Feedback";
import { Field, Input, Textarea, Toggle } from "@/components/ui/Field";
import { Segmented } from "@/components/ui/Tabs";

type S = Record<string, any>;
const NAMES: Record<Platform, string> = { linkedin: "LinkedIn", x: "X" };

function Section({ id, title, description, children, onSave, dirty, pending }: { id: string; title: string; description?: ReactNode; children: ReactNode; onSave?: () => void; dirty?: boolean; pending?: boolean }) {
  return (
    <Panel
      title={
        <span id={id} className="flex items-center gap-2">
          {title}
          {pending && <Badge tone="neutral">Applies on the next run</Badge>}
        </span>
      }
      description={description}
      actions={
        onSave && (
          <Button size="sm" variant="primary" icon={<Save className="size-4" />} onClick={onSave} disabled={!dirty}>
            Save
          </Button>
        )
      }
    >
      {children}
    </Panel>
  );
}

function useDraft<T>(initial: T): [T, (v: T) => void, boolean, () => void] {
  const [value, setValue] = useState<T>(initial);
  const key = JSON.stringify(initial);
  useEffect(() => setValue(initial), [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return [value, setValue, JSON.stringify(value) !== key, () => setValue(initial)];
}

function NumberField({ label, value, onChange, min, max, step = 1, hint, id }: { label: string; value: number; onChange: (n: number) => void; min?: number; max?: number; step?: number; hint?: string; id: string }) {
  return (
    <Field label={label} htmlFor={id} hint={hint}>
      <Input id={id} type="number" value={Number.isFinite(value) ? value : ""} min={min} max={max} step={step} onChange={(e) => onChange(Number(e.target.value))} className="w-32" />
    </Field>
  );
}

function ProfileSection({ settings }: { settings: S }) {
  const act = useDesk((s) => s.act);
  const pending = useDesk((s) => s.pending.profile);
  const [text, setText, dirty] = useDraft<string>(settings.profile ?? "");
  return (
    <Section id="profile" title="Profile" description="The only facts about you the drafter may use. Never name your employer, clients or colleagues here." onSave={() => act({ type: "profile.update", text }, { toast: "Profile saved." })} dirty={dirty} pending={pending}>
      <Textarea aria-label="Profile" value={text} onChange={(e) => setText(e.target.value)} minRows={8} className="font-mono text-[13px]" />
    </Section>
  );
}

function VolumeSection({ settings }: { settings: S }) {
  const act = useDesk((s) => s.act);
  const pending = useDesk((s) => s.pending.settings);
  const initial = useMemo(
    () => ({
      li: { ...settings.platforms?.linkedin },
      x: { ...settings.platforms?.x },
      earliest: settings.delivery?.earliest_local_time ?? "04:00",
    }),
    [settings],
  );
  const [v, setV, dirty] = useDraft(initial);
  const save = () =>
    act(
      {
        type: "settings.update",
        patch: {
          platforms: {
            linkedin: { enabled: v.li.enabled, slots: v.li.slots, min_slots: Math.min(v.li.min_slots, v.li.slots), max_interview_per_day: v.li.max_interview_per_day },
            x: {
              enabled: v.x.enabled,
              slots: v.x.slots,
              min_slots: Math.min(v.x.min_slots, v.x.slots),
              max_interview_per_day: v.x.max_interview_per_day,
              reply_slots: v.x.reply_slots,
              reply_until_followers: v.x.reply_until_followers,
              premium: v.x.premium,
            },
          },
          delivery: { earliest_local_time: v.earliest },
        },
      },
      { toast: "Saved. The next delivery uses it." },
    );
  return (
    <Section id="volume" title="Volume and schedule" description="How many cards arrive each morning. Cutting LinkedIn to 4–5 posts a week is the fallback before quality drops." onSave={save} dirty={dirty} pending={pending}>
      <div className="grid gap-6 md:grid-cols-2">
        {(["li", "x"] as const).map((k) => {
          const p = v[k];
          const set = (patch: S) => setV({ ...v, [k]: { ...p, ...patch } });
          return (
            <div key={k} className="space-y-3">
              <Toggle checked={!!p.enabled} onChange={(b) => set({ enabled: b })} label={`${k === "li" ? "LinkedIn" : "X"} cards`} />
              <div className="grid grid-cols-2 gap-3">
                <NumberField id={`${k}-slots`} label="Cards per morning" value={p.slots} min={1} max={k === "li" ? 6 : 10} onChange={(n) => set({ slots: n })} />
                <NumberField id={`${k}-min`} label="Minimum when quota is short" value={p.min_slots} min={1} max={p.slots} onChange={(n) => set({ min_slots: n })} />
                <NumberField id={`${k}-int`} label="Needs-input cards per day" value={p.max_interview_per_day} min={0} max={3} onChange={(n) => set({ max_interview_per_day: n })} />
                {k === "x" && <NumberField id="x-reply" label="Reply-angle slots" value={p.reply_slots} min={0} max={6} onChange={(n) => set({ reply_slots: n })} />}
              </div>
              {k === "x" && (
                <>
                  <NumberField id="x-until" label="Reply angles until followers reach" value={p.reply_until_followers} min={0} onChange={(n) => set({ reply_until_followers: n })} />
                  <Toggle checked={!!p.premium} onChange={(b) => set({ premium: b })} label="X Premium" description="Allows posts longer than 280 characters." />
                </>
              )}
            </div>
          );
        })}
      </div>
      <div className="mt-5 border-t border-border pt-4">
        <Field label="Deliver from (Melbourne time)" htmlFor="earliest" hint="The morning run delivers on or after this time. The schedule itself runs at about 5:40am AEDT / 4:40am AEST.">
          <Input id="earliest" type="time" value={v.earliest} onChange={(e) => setV({ ...v, earliest: e.target.value })} className="w-32" />
        </Field>
      </div>
    </Section>
  );
}

function StrategySection({ settings }: { settings: S }) {
  const act = useDesk((s) => s.act);
  const pending = useDesk((s) => s.pending.settings);
  const initial = useMemo(() => {
    const out: Record<string, Record<string, number>> = {};
    for (const p of ["linkedin", "x"]) {
      out[p] = Object.fromEntries(Object.entries((settings.strategy?.[p] ?? {}) as S).map(([k, v]) => [k, Math.round((v.weight ?? 0) * 100)]));
    }
    return out;
  }, [settings]);
  const [w, setW, dirty] = useDraft(initial);
  const save = () => {
    const patch: S = { strategy: {} };
    for (const p of ["linkedin", "x"]) {
      const total = Object.values(w[p]).reduce((a, b) => a + b, 0) || 1;
      patch.strategy[p] = Object.fromEntries(Object.entries(w[p]).map(([k, v]) => [k, { weight: Math.round((v / total) * 1000) / 1000 }]));
    }
    act({ type: "settings.update", patch }, { toast: "Starting weights saved. The learner keeps adjusting the mix from what you pick." });
  };
  return (
    <Section id="strategy" title="Pillars and lanes" description="Starting weights for the mix. They're priors: the learner moves the actual mix with evidence. Weights are normalised to 100%." onSave={save} dirty={dirty} pending={pending}>
      <div className="grid gap-6 md:grid-cols-2">
        {(["linkedin", "x"] as const).map((p) => {
          const total = Object.values(w[p] ?? {}).reduce((a, b) => a + b, 0) || 1;
          return (
            <div key={p}>
              <div className="mb-2 text-[13px] font-semibold text-muted">{NAMES[p]}</div>
              <ul className="space-y-2">
                {Object.entries((settings.strategy?.[p] ?? {}) as S).map(([k, pillar]) => (
                  <li key={k} className="flex items-center gap-3">
                    <label htmlFor={`w-${p}-${k}`} className="min-w-0 flex-1 text-[13.5px]">
                      {pillar.label}
                      <span className="block text-[12px] text-muted">{pillar.mode === "interview" ? "Interview mode" : "Drafted from sources"}</span>
                    </label>
                    <Input id={`w-${p}-${k}`} type="number" min={0} max={100} value={w[p]?.[k] ?? 0} onChange={(e) => setW({ ...w, [p]: { ...w[p], [k]: Math.max(0, Number(e.target.value)) } })} className="w-20" />
                    <span className="w-12 text-right text-[12px] text-muted tabular-nums">{Math.round(((w[p]?.[k] ?? 0) / total) * 100)}%</span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function RewardsSection({ settings }: { settings: S }) {
  const act = useDesk((s) => s.act);
  const pending = useDesk((s) => s.pending.settings);
  const labels: Record<string, string> = {
    followers_gained: "Followers gained",
    profile_views: "Profile views",
    comments: "Comments / replies",
    reposts: "Reposts (+ sends)",
    impressions: "Impressions / views",
    reactions: "Reactions / likes",
  };
  const initial = useMemo(() => {
    const out: Record<string, Record<string, number>> = {};
    for (const p of ["linkedin", "x"]) out[p] = Object.fromEntries(Object.entries((settings.rewards?.[p] ?? {}) as Record<string, number>).map(([k, v]) => [k, Math.round(v * 100)]));
    return out;
  }, [settings]);
  const [w, setW, dirty] = useDraft(initial);
  const save = () => {
    const patch: S = { rewards: {} };
    for (const p of ["linkedin", "x"]) {
      const total = Object.values(w[p]).reduce((a, b) => a + b, 0) || 1;
      patch.rewards[p] = Object.fromEntries(Object.entries(w[p]).map(([k, v]) => [k, Math.round((v / total) * 1000) / 1000]));
    }
    act({ type: "settings.update", patch }, { toast: "Reward weights saved." });
  };
  return (
    <Section id="rewards" title="Reward weights" description="How a post's result is scored, relative to your own median. Yours to change: the learner never changes these." onSave={save} dirty={dirty} pending={pending}>
      <div className="grid gap-6 md:grid-cols-2">
        {(["linkedin", "x"] as const).map((p) => (
          <div key={p}>
            <div className="mb-2 text-[13px] font-semibold text-muted">{NAMES[p]}</div>
            <ul className="space-y-2">
              {Object.keys(w[p] ?? {}).map((k) => (
                <li key={k} className="flex items-center gap-3">
                  <label htmlFor={`r-${p}-${k}`} className="flex-1 text-[13.5px]">
                    {labels[k] ?? k}
                  </label>
                  <Input id={`r-${p}-${k}`} type="number" min={0} max={100} value={w[p][k]} onChange={(e) => setW({ ...w, [p]: { ...w[p], [k]: Math.max(0, Number(e.target.value)) } })} className="w-20" />
                  <span className="w-6 text-[12px] text-muted">%</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Section>
  );
}

function LearningSection({ settings }: { settings: S }) {
  const act = useDesk((s) => s.act);
  const pending = useDesk((s) => s.pending.settings);
  const initial = useMemo(() => ({ explore: Math.round((settings.learning?.explore_rate ?? 0.2) * 100), half: settings.learning?.half_life_days ?? 42, frozen: !!settings.learning?.frozen }), [settings]);
  const [v, setV, dirty] = useDraft(initial);
  return (
    <Section
      id="learning"
      title="Learning"
      description="Exploration keeps testing new mixes; the half-life decides how fast old results fade."
      onSave={() => act({ type: "settings.update", patch: { learning: { explore_rate: v.explore / 100, half_life_days: v.half, frozen: v.frozen } } }, { toast: "Learning settings saved." })}
      dirty={dirty}
      pending={pending}
    >
      <div className="flex flex-wrap gap-6">
        <NumberField id="explore" label="Exploration (% of slots)" value={v.explore} min={0} max={80} onChange={(n) => setV({ ...v, explore: n })} />
        <NumberField id="half" label="Half-life (days)" value={v.half} min={3} max={365} onChange={(n) => setV({ ...v, half: n })} />
      </div>
      <div className="mt-4 max-w-md">
        <Toggle checked={v.frozen} onChange={(b) => setV({ ...v, frozen: b })} label="Freeze learning" description="Keeps the current mix while you review the playbook by hand (the fallback if learning overfits)." />
      </div>
    </Section>
  );
}

function ModelsSection({ settings }: { settings: S }) {
  const act = useDesk((s) => s.act);
  const pending = useDesk((s) => s.pending.settings);
  const providers = (settings.llm?.providers ?? {}) as S;
  const initial = useMemo(
    () => ({
      route: [...((settings.llm?.routes?.draft ?? []) as string[])],
      cap: settings.llm?.daily_cap ?? 60,
      models: Object.fromEntries(Object.entries(providers).map(([k, p]) => [k, p.model as string])),
    }),
    [settings, providers],
  );
  const [v, setV, dirty] = useDraft(initial);
  const move = (i: number, d: -1 | 1) => {
    const r = [...v.route];
    const j = i + d;
    if (j < 0 || j >= r.length) return;
    [r[i], r[j]] = [r[j], r[i]];
    setV({ ...v, route: r });
  };
  const save = () => {
    const modelPatch = Object.fromEntries(Object.entries(v.models).filter(([k, m]) => m && m !== providers[k]?.model).map(([k, m]) => [k, { model: m }]));
    act({ type: "settings.update", patch: { llm: { daily_cap: v.cap, routes: { draft: v.route }, ...(Object.keys(modelPatch).length ? { providers: modelPatch } : {}) } } }, { toast: "Model settings saved." });
  };
  return (
    <Section id="models" title="Models" description="Free providers are tried in order; when one hits its daily quota, the next takes over. Switching the drafter to a paid model is a change here." onSave={save} dirty={dirty} pending={pending}>
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <div className="mb-2 text-[13px] font-semibold">Drafting order</div>
          <ol className="space-y-1.5">
            {v.route.map((name, i) => (
              <li key={name} className="flex items-center gap-2 rounded-lg border border-border px-2.5 py-1.5 text-[13px]">
                <span className="w-5 text-muted tabular-nums">{i + 1}.</span>
                <span className="flex-1">
                  {name} <span className="text-muted">· {providers[name]?.model}</span>
                </span>
                {!providers[name]?.trains_on_inputs && <Badge tone="ok">No training on prompts</Badge>}
                <IconButton size="sm" label="Move up" icon={<ArrowUp className="size-4" />} onClick={() => move(i, -1)} disabled={i === 0} />
                <IconButton size="sm" label="Move down" icon={<ArrowDown className="size-4" />} onClick={() => move(i, 1)} disabled={i === v.route.length - 1} />
              </li>
            ))}
          </ol>
          <div className="mt-4">
            <NumberField id="cap" label="Daily call cap (all providers)" value={v.cap} min={0} max={2000} onChange={(n) => setV({ ...v, cap: n })} />
          </div>
        </div>
        <div>
          <div className="mb-2 text-[13px] font-semibold">Model per provider</div>
          <ul className="space-y-2">
            {Object.entries(providers).map(([k, p]) => (
              <li key={k} className="grid grid-cols-[7rem_1fr] items-center gap-2">
                <label htmlFor={`model-${k}`} className="text-[13px] text-muted">
                  {k}
                </label>
                <Input id={`model-${k}`} value={v.models[k] ?? ""} onChange={(e) => setV({ ...v, models: { ...v.models, [k]: e.target.value } })} className="h-9" aria-describedby={`key-${k}`} />
                <span id={`key-${k}`} className="col-start-2 -mt-1 text-[11.5px] text-faint">
                  key: {p.api_key_env || "none"} · {p.daily_limit}/day
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Section>
  );
}

function WatchlistSection({ settings }: { settings: S }) {
  const act = useDesk((s) => s.act);
  const pending = useDesk((s) => s.pending.settings);
  const initial = useMemo(() => Object.fromEntries(Object.entries((settings.watchlist ?? {}) as Record<string, string[]>).map(([k, v]) => [k, v.join(", ")])), [settings]);
  const [v, setV, dirty] = useDraft<Record<string, string>>(initial);
  const save = () => {
    const patch = Object.fromEntries(Object.entries(v).map(([k, s]) => [k, s.split(/[\s,]+/).map((h) => h.replace(/^@/, "").trim()).filter(Boolean)]));
    act({ type: "settings.update", patch: { watchlist: patch } }, { toast: "Watchlist saved." });
  };
  return (
    <Section id="watchlist" title="X watchlist" description="Large accounts likely to post about the day's biggest news. Reply cards link to a live X search of their posts." onSave={save} dirty={dirty} pending={pending}>
      <div className="grid gap-4 md:grid-cols-2">
        {Object.keys(v).map((lane) => (
          <Field key={lane} label={lane[0].toUpperCase() + lane.slice(1)} htmlFor={`wl-${lane}`}>
            <Textarea id={`wl-${lane}`} value={v[lane]} onChange={(e) => setV({ ...v, [lane]: e.target.value })} minRows={2} placeholder="handle, handle, …" />
          </Field>
        ))}
      </div>
    </Section>
  );
}

function GuardSection() {
  const raw = useDesk((s) => s.guardTerms);
  const setRaw = useDesk((s) => s.setGuardTerms);
  const [v, setV] = useState(raw);
  const terms = parseTerms(v);
  return (
    <Section id="guard" title="Guard terms (this device only)" description="Employer, clients, internal system names, colleagues. Checked live while you edit. Stored only in this browser, never uploaded. The pipeline uses your PBS_BLOCKLIST secret.">
      <Textarea aria-label="Guard terms, one per line" value={v} onChange={(e) => setV(e.target.value)} minRows={4} placeholder="One term per line" className="font-mono text-[13px]" />
      <div className="mt-3 flex items-center justify-between">
        <span className="text-[12.5px] text-muted">{terms.length} term(s)</span>
        <Button size="sm" variant="primary" onClick={() => setRaw(v)} disabled={v === raw}>
          Save on this device
        </Button>
      </div>
    </Section>
  );
}

function ConnectionSection() {
  const conn = useDesk((s) => s.connection);
  const disconnect = useDesk((s) => s.disconnect);
  const view = useDesk((s) => s.view);
  const clearOutbox = useDesk((s) => s.clearOutbox);
  const outbox = useDesk((s) => s.outbox);
  const toast = useDesk((s) => s.toast);
  const download = () => {
    const blob = new Blob([JSON.stringify(view, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `pbs-desk-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  const clearDrafts = () => {
    for (const k of keysWithPrefix("pbs.work.")) remove(k);
    for (const k of keysWithPrefix("pbs.answers.")) remove(k);
    toast("ok", "Local drafts cleared.");
  };
  return (
    <Section id="connection" title="Connection and data">
      {conn?.mode === "github" ? (
        <dl className="grid grid-cols-[9rem_1fr] gap-y-1.5 text-[13.5px]">
          <dt className="text-muted">Data repo</dt>
          <dd>
            {conn.dataRepo} <span className="text-muted">({conn.dataBranch})</span>
          </dd>
          <dt className="text-muted">Pipeline</dt>
          <dd>
            {conn.codeRepo} · {conn.workflow} <span className="text-muted">({conn.codeRef})</span>
          </dd>
          <dt className="text-muted">Token</dt>
          <dd>•••• {conn.token.slice(-4)} (stored in this browser)</dd>
          <dt className="text-muted">Device</dt>
          <dd>{conn.device}</dd>
        </dl>
      ) : (
        <p className="text-[13.5px] text-muted">Demo mode: nothing is connected.</p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button onClick={() => navigate("/connect")}>{conn?.mode === "github" ? "Change connection" : "Connect"}</Button>
        <Button icon={<Download className="size-4" />} onClick={download} disabled={!view}>
          Download desk data
        </Button>
        <Button variant="ghost" onClick={clearDrafts}>
          Clear local drafts
        </Button>
        {outbox.length > 0 && (
          <Button
            variant="ghost"
            onClick={() => {
              if (window.confirm(`Discard ${outbox.length} unsynced change(s)?`)) clearOutbox();
            }}
          >
            Discard unsynced changes ({outbox.length})
          </Button>
        )}
        {conn?.mode === "github" && (
          <Button
            variant="danger"
            icon={<LogOut className="size-4" />}
            onClick={() => {
              if (window.confirm("Forget the token on this device? Unsynced changes stay queued until you reconnect.")) {
                disconnect();
                navigate("/connect");
              }
            }}
          >
            Forget token
          </Button>
        )}
      </div>
    </Section>
  );
}

function AppearanceSection() {
  const prefs = useDesk((s) => s.prefs);
  const setPrefs = useDesk((s) => s.setPrefs);
  return (
    <Section id="appearance" title="Appearance">
      <Segmented
        label="Theme"
        value={prefs.theme}
        onChange={(t) => setPrefs({ theme: t })}
        items={[
          { value: "system", label: "System" },
          { value: "light", label: "Light" },
          { value: "dark", label: "Dark" },
        ]}
      />
    </Section>
  );
}

export function Settings() {
  const settings = useDesk((s) => s.view?.settings) as S | undefined;
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted">Changes are validated by the pipeline; an invalid one is rejected with the reason on the System page.</p>
      </header>
      {settings ? (
        <>
          <ProfileSection settings={settings} />
          <VolumeSection settings={settings} />
          <StrategySection settings={settings} />
          <RewardsSection settings={settings} />
          <LearningSection settings={settings} />
          <ModelsSection settings={settings} />
          <WatchlistSection settings={settings} />
        </>
      ) : (
        <p className="text-sm text-muted">Pipeline settings appear after the first run.</p>
      )}
      <GuardSection />
      <AppearanceSection />
      <ConnectionSection />
    </div>
  );
}

import { useState } from "react";
import { KeyRound, Trash2 } from "lucide-react";
import { listModels, StudioError } from "@/lib/studio/gemini";
import { cachedModels, clearStudioKey, getStudioKey, keyHint, setStudioKey, spentModels } from "@/lib/studio/settings";
import { useDesk } from "@/state/store";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";

/** The Studio's Gemini key: checked against Gemini, then kept on this device only. */
export function StudioKeyPanel({ onReady, compact }: { onReady?: (models: string[]) => void; compact?: boolean }) {
  const toast = useDesk((s) => s.toast);
  const [saved, setSaved] = useState(getStudioKey);
  const [key, setKey] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const check = async () => {
    const k = key.trim();
    if (!k) return;
    setChecking(true);
    setError(null);
    try {
      const models = await listModels(k);
      setStudioKey(k, models);
      setSaved(k);
      setKey("");
      toast("ok", `Studio is ready (${models[0]}).`);
      onReady?.(models);
    } catch (e) {
      setError(e instanceof StudioError ? e.message : "Couldn't check the key.");
    } finally {
      setChecking(false);
    }
  };
  return (
    <div className="space-y-3">
      {saved ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border px-3 py-2 text-[13.5px]">
          <span className="min-w-0">
            <span className="flex items-center gap-1.5">
              <KeyRound className="size-4 text-ok" aria-hidden /> Gemini key {keyHint(saved)} saved on this device.
            </span>
            {(cachedModels(saved) ?? []).length > 0 && (
              <span className="mt-0.5 block text-xs text-muted">
                Models, tried in order: {(cachedModels(saved) ?? []).map((m) => (spentModels().includes(m) ? `${m} (out of today's quota)` : m)).join(", ")}
              </span>
            )}
          </span>
          <Button
            size="sm"
            variant="ghost"
            icon={<Trash2 className="size-4" />}
            onClick={() => {
              clearStudioKey();
              setSaved("");
            }}
          >
            Remove
          </Button>
        </div>
      ) : (
        !compact && <p className="text-[13.5px] text-muted">The Studio talks to Gemini straight from this device, so replies start in a second or two. It needs a free Gemini API key.</p>
      )}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void check();
        }}
      >
        <Field label={saved ? "Replace the key" : "Gemini API key"} htmlFor="studio-key" error={error} className="min-w-0 flex-1">
          <Input id="studio-key" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder="AIza…" />
        </Field>
        <Button type="submit" variant="primary" loading={checking} disabled={!key.trim()}>
          Check and save
        </Button>
      </form>
      <ul className="list-disc space-y-1 pl-5 text-xs text-muted">
        <li>
          Get one free at{" "}
          <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer" className="text-accent hover:underline">
            aistudio.google.com/apikey
          </a>
          . Make it in a different Google Cloud project from the pipeline's <code>GEMINI_API_KEY</code>, so chatting never uses up the morning's free quota.
        </li>
        <li>The key stays in this browser, like your GitHub token. Your chats stay on this device too, unless you save a post to the board.</li>
        <li>What you send goes to Google's Gemini API. On the free tier Google may use it to improve its models, so don't paste anything confidential. Your guard terms are replaced with “[redacted]” before anything is sent.</li>
      </ul>
    </div>
  );
}

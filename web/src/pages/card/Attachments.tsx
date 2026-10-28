import { useEffect, useState } from "react";
import { Download, ImageIcon, Share2 } from "lucide-react";
import type { Attachment } from "@/types";
import { downloadBlob } from "@/lib/visual/export";
import { useDesk } from "@/state/store";
import { Button } from "@/components/ui/Button";
import { canShareFiles } from "@/components/VisualViewer";

async function toFile(dataUrl: string, name: string): Promise<File> {
  const blob = await (await fetch(dataUrl)).blob();
  return new File([blob], name, { type: blob.type || "image/jpeg" });
}

/** Pictures saved with a Studio post: shown here to download, or share to the app on a phone. */
export function Attachments({ items, slug }: { items: Attachment[]; slug: string }) {
  const loadMedia = useDesk((s) => s.loadMedia);
  const toast = useDesk((s) => s.toast);
  const [srcs, setSrcs] = useState<Record<string, string | null>>({});
  useEffect(() => {
    let live = true;
    for (const a of items) void loadMedia(a.path).then((src) => live && setSrcs((cur) => ({ ...cur, [a.path]: src })));
    return () => {
      live = false;
    };
  }, [items, loadMedia]);
  const ready = items.map((a) => srcs[a.path]).filter((s): s is string => !!s);
  const name = (i: number) => `${slug}-${i + 1}.jpg`;
  const share = async () => {
    try {
      await navigator.share({ files: await Promise.all(ready.map((s, i) => toFile(s, name(i)))) });
    } catch (e) {
      if ((e as Error)?.name !== "AbortError") toast("bad", "Couldn't share the pictures: download them instead.");
    }
  };
  const download = async () => {
    for (const [i, s] of ready.entries()) downloadBlob((await toFile(s, name(i))) as Blob, name(i));
  };
  const shareable = typeof File !== "undefined" && canShareFiles([new File([""], "x.jpg", { type: "image/jpeg" })]);
  return (
    <section aria-label="Pictures" className="space-y-2 rounded-2xl border border-border bg-surface p-3">
      <h3 className="flex items-center gap-1.5 text-[13px] font-semibold">
        <ImageIcon className="size-4 text-accent" aria-hidden /> Pictures to post with it
      </h3>
      <div className="flex flex-wrap gap-2">
        {items.map((a, i) =>
          srcs[a.path] ? (
            <img key={a.path} src={srcs[a.path]!} alt={`Picture ${i + 1}`} className="h-28 w-auto rounded-lg border border-border object-cover" />
          ) : (
            <div key={a.path} className="flex h-28 w-24 items-center justify-center rounded-lg bg-surface-2 text-xs text-muted">
              {a.path in srcs ? "Not available" : "Loading…"}
            </div>
          ),
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {shareable && (
          <Button size="sm" variant="primary" icon={<Share2 className="size-4" />} onClick={() => void share()} disabled={!ready.length}>
            Share pictures
          </Button>
        )}
        <Button size="sm" icon={<Download className="size-4" />} onClick={() => void download()} disabled={!ready.length}>
          Download
        </Button>
      </div>
    </section>
  );
}

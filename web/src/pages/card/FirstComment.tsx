import { Copy, MessageSquare } from "lucide-react";
import type { Platform } from "@/types";
import { copyText } from "@/lib/compose";
import { useDesk } from "@/state/store";
import { Button } from "@/components/ui/Button";

/** The source link goes here instead of the post: both platforms tend to show posts with links to fewer people. */
export function FirstComment({ platform, text }: { platform: Platform; text: string }) {
  const toast = useDesk((s) => s.toast);
  const copy = async () => {
    const ok = await copyText(text);
    toast(ok ? "ok" : "bad", ok ? "Copied. Post it as the first comment right after the post." : "Couldn't copy. Select the text and copy it manually.");
  };
  return (
    <div className="space-y-2 rounded-2xl border border-border bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-[13px] font-semibold">
          <MessageSquare className="size-4 text-accent" aria-hidden /> {platform === "linkedin" ? "First comment" : "Reply to your post"}
        </h3>
        <Button size="sm" variant="secondary" icon={<Copy className="size-4" />} onClick={() => void copy()} aria-label={platform === "linkedin" ? "Copy the first comment" : "Copy the reply"}>
          Copy
        </Button>
      </div>
      <p className="draft-text text-[13.5px] break-words">{text}</p>
      <p className="text-xs text-muted">
        {platform === "linkedin" ? "Post this as the first comment, right after the post: links in the post itself get shown to fewer people." : "Reply to your own post with this: links in the main post get shown to fewer people."}
      </p>
    </div>
  );
}

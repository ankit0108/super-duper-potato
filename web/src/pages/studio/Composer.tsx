import { forwardRef, useImperativeHandle, useLayoutEffect, useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";
import { ArrowUp, Camera, FileText, ImagePlus, Loader2, Square, X } from "lucide-react";
import type { StudioContext, StudioImage } from "@/lib/studio/chats";
import { MAX_IMAGES, prepImage } from "@/lib/studio/images";
import type { QuickAction } from "@/lib/studio/prompt";
import { useMediaQuery } from "@/state/hooks";
import { useDesk } from "@/state/store";
import { IconButton, cx } from "@/components/ui/Button";

export type ComposerHandle = { focus: () => void; pickImages: () => void; addFiles: (files: Blob[]) => Promise<void> };

/**
 * Where you write to the Studio: text, pictures (pick, take, paste or drop them), what the message is about (a
 * card or a shared post), and the quick actions. Enter sends on a keyboard; on a phone it's a new line.
 */
export const Composer = forwardRef<
  ComposerHandle,
  {
    value: string;
    onChange: (v: string) => void;
    images: StudioImage[];
    onImages: (imgs: StudioImage[]) => void;
    context: StudioContext | null;
    onClearContext: () => void;
    chips: QuickAction[];
    onChip: (a: QuickAction) => void;
    onSend: () => void;
    onStop: () => void;
    streaming: boolean;
  }
>(function Composer({ value, onChange, images, onImages, context, onClearContext, chips, onChip, onSend, onStop, streaming }, ref) {
  const toast = useDesk((s) => s.toast);
  const text = useRef<HTMLTextAreaElement>(null);
  const pick = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);
  const [reading, setReading] = useState(false);
  const touch = useMediaQuery("(pointer: coarse)");
  const imagesRef = useRef(images);
  imagesRef.current = images;
  // Grow with the text, up to about eight lines.
  useLayoutEffect(() => {
    const el = text.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 224)}px`;
  }, [value]);

  const addFiles = async (files: Blob[]) => {
    const pics = files.filter((f) => f.type.startsWith("image/"));
    if (!pics.length) return;
    const room = MAX_IMAGES - imagesRef.current.length;
    if (room <= 0) return toast("warn", `Up to ${MAX_IMAGES} pictures per message.`);
    if (pics.length > room) toast("warn", `Added the first ${room}: up to ${MAX_IMAGES} pictures per message.`);
    setReading(true);
    try {
      const prepared: StudioImage[] = [];
      for (const f of pics.slice(0, room)) {
        try {
          prepared.push(await prepImage(f, f instanceof File ? f.name : ""));
        } catch {
          toast("bad", "One picture couldn't be read.");
        }
      }
      onImages([...imagesRef.current, ...prepared]);
    } finally {
      setReading(false);
    }
  };
  useImperativeHandle(ref, () => ({ focus: () => text.current?.focus(), pickImages: () => pick.current?.click(), addFiles }));

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !touch && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!streaming) onSend();
    }
  };
  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(e.clipboardData.files ?? []);
    if (files.some((f) => f.type.startsWith("image/"))) {
      e.preventDefault();
      void addFiles(files);
    }
  };
  const canSend = !!(value.trim() || images.length || context) && !reading;

  return (
    <div className="space-y-2">
      {chips.length > 0 && (
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-0.5" role="group" aria-label="Quick actions">
          {chips.map((c) => (
            <button
              key={c.label}
              type="button"
              disabled={streaming}
              onClick={() => onChip(c)}
              className="shrink-0 rounded-full border border-border bg-surface px-3 py-1.5 text-[13px] font-medium whitespace-nowrap text-text hover:border-accent hover:text-accent disabled:opacity-50"
            >
              {c.label}
            </button>
          ))}
        </div>
      )}
      <div className="rounded-2xl border border-border bg-surface shadow-sm focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/15">
        {(context || images.length > 0 || reading) && (
          <div className="flex flex-wrap items-center gap-2 border-b border-border p-2">
            {context && (
              <span className="inline-flex max-w-full items-center gap-1.5 rounded-lg bg-surface-2 py-1 pr-1 pl-2 text-[12.5px]">
                <FileText className="size-3.5 shrink-0 text-muted" aria-hidden />
                <span className="truncate">{context.title}</span>
                <IconButton size="sm" label="Remove" icon={<X className="size-3.5" />} onClick={onClearContext} className="size-6" />
              </span>
            )}
            {images.map((img, i) => (
              <span key={img.id} className="relative">
                <img src={img.dataUrl} alt={`Picture ${i + 1}`} className="size-14 rounded-lg object-cover" />
                <button type="button" aria-label={`Remove picture ${i + 1}`} onClick={() => onImages(images.filter((x) => x.id !== img.id))} className="absolute -top-1.5 -right-1.5 rounded-full bg-text p-0.5 text-bg">
                  <X className="size-3" />
                </button>
              </span>
            ))}
            {reading && <Loader2 className="size-4 animate-spin text-muted" aria-label="Reading the pictures" />}
          </div>
        )}
        <textarea
          ref={text}
          aria-label="Message the Studio"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKey}
          onPaste={onPaste}
          rows={1}
          placeholder={images.length ? "What should it do with these?" : "Ask anything, share a link or a picture, or say what to post about…"}
          className="block max-h-56 min-h-[2.75rem] w-full resize-none bg-transparent px-3 pt-2.5 text-[15px] leading-relaxed placeholder:text-faint focus:outline-none"
        />
        <div className="flex items-center justify-between gap-2 px-1.5 pb-1.5">
          <div className="flex items-center">
            <IconButton size="sm" label="Add pictures" icon={<ImagePlus className="size-[18px]" />} onClick={() => pick.current?.click()} disabled={streaming} />
            {touch && <IconButton size="sm" label="Take a photo" icon={<Camera className="size-[18px]" />} onClick={() => camera.current?.click()} disabled={streaming} />}
            <input
              ref={pick}
              type="file"
              accept="image/*"
              multiple
              className="sr-only"
              tabIndex={-1}
              aria-hidden
              onChange={(e) => {
                void addFiles(Array.from(e.target.files ?? []));
                e.target.value = "";
              }}
            />
            <input
              ref={camera}
              type="file"
              accept="image/*"
              capture="environment"
              className="sr-only"
              tabIndex={-1}
              aria-hidden
              onChange={(e) => {
                void addFiles(Array.from(e.target.files ?? []));
                e.target.value = "";
              }}
            />
          </div>
          {streaming ? (
            <button type="button" onClick={onStop} aria-label="Stop" title="Stop" className="flex size-9 items-center justify-center rounded-full bg-text text-bg">
              <Square className="size-3.5 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={onSend}
              disabled={!canSend}
              aria-label="Send"
              title={touch ? "Send" : "Send (Enter)"}
              className={cx("flex size-9 items-center justify-center rounded-full transition-colors", canSend ? "bg-accent text-accent-fg" : "bg-surface-3 text-faint")}
            >
              <ArrowUp className="size-5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
});

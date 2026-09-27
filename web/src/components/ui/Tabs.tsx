import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { cx } from "./Button";

export type TabItem<T extends string> = { value: T; label: ReactNode; count?: number };

/** Accessible tabs with arrow-key navigation (roving tabindex). */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
  className,
  compact,
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  className?: string;
  /** Tighter tabs for narrow panels, so every tab stays visible. */
  compact?: boolean;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const onKey = (e: KeyboardEvent, i: number) => {
    let next = -1;
    if (e.key === "ArrowRight") next = (i + 1) % items.length;
    if (e.key === "ArrowLeft") next = (i - 1 + items.length) % items.length;
    if (e.key === "Home") next = 0;
    if (e.key === "End") next = items.length - 1;
    if (next >= 0) {
      e.preventDefault();
      onChange(items[next].value);
      refs.current[next]?.focus();
    }
  };
  return (
    <div role="tablist" aria-label={label} className={cx("flex overflow-x-auto border-b border-border scrollbar-thin", compact ? "gap-0" : "gap-1", className)}>
      {items.map((it, i) => {
        const selected = it.value === value;
        return (
          <button
            key={it.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            role="tab"
            type="button"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(it.value)}
            onKeyDown={(e) => onKey(e, i)}
            className={cx(
              "-mb-px flex shrink-0 items-center gap-1.5 border-b-2 py-2 font-medium transition-colors",
              compact ? "px-2 text-[13px]" : "px-3 text-sm",
              selected ? "border-accent text-text" : "border-transparent text-muted hover:text-text",
            )}
          >
            {it.label}
            {it.count != null && it.count > 0 && <span className="rounded-full bg-surface-3 px-1.5 text-[11px] tabular-nums text-muted">{it.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function Segmented<T extends string>({ items, value, onChange, label }: { items: TabItem<T>[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-border bg-surface-2 p-0.5">
      {items.map((it) => (
        <button
          key={it.value}
          type="button"
          role="radio"
          aria-checked={it.value === value}
          onClick={() => onChange(it.value)}
          className={cx(
            "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[13px] font-medium transition-colors",
            it.value === value ? "bg-surface text-text shadow-sm" : "text-muted hover:text-text",
          )}
        >
          {it.label}
          {it.count != null && <span className="tabular-nums text-faint">{it.count}</span>}
        </button>
      ))}
    </div>
  );
}

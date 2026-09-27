import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { cx } from "./Button";

type Item = { label: ReactNode; hint?: ReactNode; onSelect: () => void; tone?: "default" | "danger" };

/** Small click-to-open menu with keyboard support and click-outside closing. */
export function Menu({ trigger, items, align = "right", label }: { trigger: (props: { onClick: () => void; "aria-expanded": boolean; "aria-haspopup": "menu"; "aria-controls": string }) => ReactNode; items: Item[]; align?: "left" | "right"; label: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    const first = ref.current?.querySelector<HTMLButtonElement>('[role="menuitem"]');
    first?.focus();
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  const onKeyDown = (e: React.KeyboardEvent) => {
    const nodes = Array.from(ref.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? []);
    const i = nodes.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      nodes[(i + 1) % nodes.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      nodes[(i - 1 + nodes.length) % nodes.length]?.focus();
    }
  };
  return (
    <div ref={ref} className="relative inline-block">
      {trigger({ onClick: () => setOpen((o) => !o), "aria-expanded": open, "aria-haspopup": "menu", "aria-controls": id })}
      {open && (
        <div
          id={id}
          role="menu"
          aria-label={label}
          onKeyDown={onKeyDown}
          className={cx(
            "absolute z-40 mt-1 min-w-52 overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-xl",
            align === "right" ? "right-0" : "left-0",
          )}
        >
          {items.map((it, i) => (
            <button
              key={i}
              role="menuitem"
              type="button"
              tabIndex={-1}
              onClick={() => {
                setOpen(false);
                it.onSelect();
              }}
              className={cx(
                "flex w-full flex-col items-start px-3 py-2 text-left text-sm hover:bg-surface-2 focus:bg-surface-2 focus:outline-none",
                it.tone === "danger" ? "text-bad" : "text-text",
              )}
            >
              <span>{it.label}</span>
              {it.hint && <span className="text-xs text-muted">{it.hint}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

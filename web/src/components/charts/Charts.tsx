// Small, dependency-free SVG charts following the dataviz method: thin marks, one axis, recessive grid,
// hover + keyboard tooltips, selective direct labels, and a table view for every chart.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { TableProperties } from "lucide-react";
import { cx } from "../ui/Button";

export type Series = { key: string; label: string; color: string; values: Array<number | null> };

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(600);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(240, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/**
 * A readable axis: steps of 1, 2 or 5 × 10ⁿ (2.5 too for fractional data), ending at or just above the data.
 * Counts use whole-number steps, so an axis never reads "3.75 posts".
 */
export function niceScale(dataMax: number, integer = false, target = 4): { max: number; ticks: number[] } {
  const top = dataMax > 0 ? dataMax : 1;
  const raw = top / target;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const multiples = integer ? [1, 2, 5, 10] : [1, 2, 2.5, 5, 10];
  let step = (multiples.find((m) => m * pow >= raw - 1e-12) ?? 10) * pow;
  if (integer) step = Math.max(1, Math.round(step));
  const max = Math.ceil(top / step - 1e-9) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= max + step / 2; v += step) ticks.push(Math.round(v * 1e9) / 1e9);
  return { max: ticks[ticks.length - 1], ticks };
}

export function LegendKey({ items }: { items: Array<{ label: string; color: string; kind?: "line" | "rect" }> }) {
  if (items.length < 2) return null;
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px] text-muted" aria-label="Legend">
      {items.map((it) => (
        <li key={it.label} className="flex items-center gap-1.5">
          {it.kind === "line" ? (
            <span className="inline-block h-0.5 w-4 rounded" style={{ background: it.color }} aria-hidden />
          ) : (
            <span className="inline-block size-2.5 rounded-sm" style={{ background: it.color }} aria-hidden />
          )}
          {it.label}
        </li>
      ))}
    </ul>
  );
}

/** Title, legend, and a table-view toggle: every chart has a table twin. */
export function ChartCard({ title, subtitle, legend, table, children }: { title: string; subtitle?: ReactNode; legend?: ReactNode; table: ReactNode; children: ReactNode }) {
  const [showTable, setShowTable] = useState(false);
  return (
    <figure className="rounded-2xl border border-border bg-surface p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <figcaption>
          <div className="text-[14px] font-semibold">{title}</div>
          {subtitle && <div className="text-[12.5px] text-muted">{subtitle}</div>}
        </figcaption>
        <button
          type="button"
          onClick={() => setShowTable((v) => !v)}
          aria-pressed={showTable}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12px] text-muted hover:bg-surface-2 hover:text-text"
        >
          <TableProperties className="size-3.5" /> {showTable ? "Chart" : "Table"}
        </button>
      </div>
      {legend && <div className="mb-2">{legend}</div>}
      {showTable ? <div className="overflow-x-auto">{table}</div> : children}
    </figure>
  );
}

export function DataTable({ columns, rows }: { columns: string[]; rows: Array<Array<ReactNode>> }) {
  return (
    <table className="w-full text-left text-[13px]">
      <thead>
        <tr className="border-b border-border text-[12px] text-muted">
          {columns.map((c, i) => (
            <th key={c} className={cx("py-1.5 font-medium", i > 0 && "text-right")}>
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-b border-border last:border-0">
            {r.map((cell, j) => (
              <td key={j} className={cx("py-1.5", j > 0 && "text-right tabular-nums")}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

type Tip = { x: number; y: number; title: string; rows: Array<{ label: string; value: string; color?: string }> } | null;

function Tooltip({ tip, width }: { tip: Tip; width: number }) {
  if (!tip) return null;
  const left = Math.min(Math.max(8, tip.x + 12), width - 180);
  return (
    <div className="pointer-events-none absolute z-10 min-w-36 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-[12px] shadow-lg" style={{ left, top: Math.max(0, tip.y - 8) }} role="status">
      <div className="mb-0.5 text-muted">{tip.title}</div>
      {tip.rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2">
          {r.color && <span className="inline-block h-0.5 w-3 rounded" style={{ background: r.color }} aria-hidden />}
          <span className="font-semibold text-text tabular-nums">{r.value}</span>
          <span className="text-muted">{r.label}</span>
        </div>
      ))}
    </div>
  );
}

const PAD = { top: 14, right: 12, bottom: 26, left: 34 };

/** Columns for one series, with an optional target line. Hover/focus a column for its value. */
export function ColumnChart({ labels, values, color, target, format = (v) => String(v), height = 170, ariaLabel }: { labels: string[]; values: number[]; color: string; target?: number; format?: (v: number) => string; height?: number; ariaLabel: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip>(null);
  const { max, ticks: yTicks } = niceScale(Math.max(target ?? 0, ...values, 1), values.every(Number.isInteger));
  const iw = width - PAD.left - PAD.right;
  const ih = height - PAD.top - PAD.bottom;
  const band = iw / Math.max(1, values.length);
  const bw = Math.min(24, band * 0.6);
  const y = (v: number) => PAD.top + ih - (v / max) * ih;
  const last = values.length - 1;
  return (
    <div ref={ref} className="relative" onPointerLeave={() => setTip(null)}>
      <svg width={width} height={height} role="img" aria-label={ariaLabel} className="block">
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth={1} />
            <text x={PAD.left - 6} y={y(t) + 3.5} textAnchor="end" className="fill-[var(--faint)] text-[10.5px] tabular-nums">
              {format(t)}
            </text>
          </g>
        ))}
        {target != null && (
          <g>
            <line x1={PAD.left} x2={width - PAD.right} y1={y(target)} y2={y(target)} stroke="var(--muted)" strokeWidth={1} />
            <text x={width - PAD.right} y={y(target) - 4} textAnchor="end" className="fill-[var(--muted)] text-[10.5px]">
              target {format(target)}
            </text>
          </g>
        )}
        {values.map((v, i) => {
          const cx0 = PAD.left + band * i + band / 2;
          const h = Math.max(0, (v / max) * ih);
          const x0 = cx0 - bw / 2;
          const top = PAD.top + ih - h;
          const r = Math.min(4, h, bw / 2);
          const path = h > 0 ? `M${x0},${PAD.top + ih} V${top + r} Q${x0},${top} ${x0 + r},${top} H${x0 + bw - r} Q${x0 + bw},${top} ${x0 + bw},${top + r} V${PAD.top + ih} Z` : "";
          const show = () => setTip({ x: cx0, y: top - 36, title: labels[i], rows: [{ label: "", value: format(v) }] });
          return (
            <g key={i}>
              {path && <path d={path} fill={color} />}
              <rect x={cx0 - band / 2} y={PAD.top} width={band} height={ih} fill="transparent" tabIndex={0} aria-label={`${labels[i]}: ${format(v)}`} onPointerMove={show} onFocus={show} onBlur={() => setTip(null)} className="focus:outline-none" />
              {i === last && v > 0 && (
                <text x={cx0} y={top - 5} textAnchor="middle" className="fill-[var(--text)] text-[11px] font-semibold">
                  {format(v)}
                </text>
              )}
              {(values.length <= 8 || i % 2 === last % 2) && (
                <text x={cx0} y={height - 8} textAnchor="middle" className="fill-[var(--faint)] text-[10.5px]">
                  {labels[i]}
                </text>
              )}
            </g>
          );
        })}
        <line x1={PAD.left} x2={width - PAD.right} y1={PAD.top + ih} y2={PAD.top + ih} stroke="var(--axis)" strokeWidth={1} />
      </svg>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}

/** Up to two series on one axis. Crosshair snaps to the nearest week; tooltip lists every series. */
export function LineChart({ labels, series, format = (v) => String(v), domainMax, height = 190, ariaLabel }: { labels: string[]; series: Series[]; format?: (v: number) => string; domainMax?: number; height?: number; ariaLabel: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const all = series.flatMap((s) => s.values.filter((v): v is number => v != null));
  const { max, ticks: yTicks } = niceScale(domainMax ?? Math.max(...all, 0.0001));
  const right = 70;
  const iw = width - PAD.left - right;
  const ih = height - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (labels.length <= 1 ? iw / 2 : (iw * i) / (labels.length - 1));
  const y = (v: number) => PAD.top + ih - (v / max) * ih;
  const pathFor = (vals: Array<number | null>) => {
    let d = "";
    let pen = false;
    vals.forEach((v, i) => {
      if (v == null) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
      pen = true;
    });
    return d.trim();
  };
  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const box = (e.currentTarget as SVGRectElement).getBoundingClientRect();
    const px = e.clientX - box.left;
    const i = Math.round((px / Math.max(1, box.width)) * (labels.length - 1));
    setHover(Math.max(0, Math.min(labels.length - 1, i)));
  };
  const tip: Tip =
    hover == null
      ? null
      : { x: x(hover), y: PAD.top, title: labels[hover], rows: series.map((s) => ({ label: s.label, value: s.values[hover] == null ? "–" : format(s.values[hover]!), color: s.color })) };
  return (
    <div ref={ref} className="relative">
      <svg width={width} height={height} role="img" aria-label={ariaLabel} className="block">
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={width - right} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth={1} />
            <text x={PAD.left - 6} y={y(t) + 3.5} textAnchor="end" className="fill-[var(--faint)] text-[10.5px] tabular-nums">
              {format(t)}
            </text>
          </g>
        ))}
        <line x1={PAD.left} x2={width - right} y1={PAD.top + ih} y2={PAD.top + ih} stroke="var(--axis)" strokeWidth={1} />
        {labels.map((l, i) =>
          labels.length <= 8 || i % 2 === (labels.length - 1) % 2 ? (
            <text key={l} x={x(i)} y={height - 8} textAnchor="middle" className="fill-[var(--faint)] text-[10.5px]">
              {l}
            </text>
          ) : null,
        )}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + ih} stroke="var(--border-strong)" strokeWidth={1} />}
        {series.map((s) => (
          <path key={s.key} d={pathFor(s.values)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {series.map((s) => {
          const i = s.values.map((v, j) => (v == null ? -1 : j)).filter((j) => j >= 0).pop();
          if (i == null || i < 0) return null;
          const v = s.values[i]!;
          return (
            <g key={`end-${s.key}`}>
              <circle cx={x(i)} cy={y(v)} r={4} fill={s.color} stroke="var(--surface)" strokeWidth={2} />
              <text x={x(i) + 8} y={y(v) + 4} className="fill-[var(--text)] text-[11px]">
                {format(v)} <tspan className="fill-[var(--muted)]">{s.label}</tspan>
              </text>
            </g>
          );
        })}
        {hover != null &&
          series.map((s) =>
            s.values[hover] == null ? null : <circle key={`h-${s.key}`} cx={x(hover)} cy={y(s.values[hover]!)} r={4} fill={s.color} stroke="var(--surface)" strokeWidth={2} />,
          )}
        <rect
          x={PAD.left}
          y={PAD.top}
          width={iw}
          height={ih}
          fill="transparent"
          tabIndex={0}
          aria-label={`${ariaLabel}. Use left and right arrow keys to read values.`}
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
          onFocus={() => setHover(labels.length - 1)}
          onBlur={() => setHover(null)}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? labels.length - 1) - 1));
            if (e.key === "ArrowRight") setHover((h) => Math.min(labels.length - 1, (h ?? 0) + 1));
          }}
          className="focus:outline-none"
        />
      </svg>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}

/** Did Ankit post on each of the last N days? One row per platform. */
export function DaysGrid({ days, rows }: { days: string[]; rows: Array<{ label: string; color: string; values: number[] }> }) {
  const [tip, setTip] = useState<string | null>(null);
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2">
          <span className="w-16 shrink-0 text-[12px] text-muted">{r.label}</span>
          <div className="grid flex-1 gap-[2px]" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
            {days.map((d, i) => {
              const n = r.values[i] ?? 0;
              const label = `${r.label} ${d}: ${n ? `${n} post${n === 1 ? "" : "s"}` : "no post"}`;
              return (
                <span
                  key={d}
                  tabIndex={0}
                  role="img"
                  aria-label={label}
                  onPointerEnter={() => setTip(label)}
                  onFocus={() => setTip(label)}
                  onPointerLeave={() => setTip(null)}
                  onBlur={() => setTip(null)}
                  className="h-5 rounded-[3px] focus:outline-2 focus:outline-accent"
                  style={{ background: n ? r.color : "var(--surface-3)" }}
                />
              );
            })}
          </div>
        </div>
      ))}
      <p className="min-h-4 text-[12px] text-muted" aria-live="polite">
        {tip ?? "Each square is a day, oldest on the left."}
      </p>
    </div>
  );
}

export function Sparkline({ values, width = 96, height = 28 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i: number) => (width * i) / (values.length - 1);
  const y = (v: number) => height - 3 - ((v - min) / span) * (height - 6);
  const d = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = values.length - 1;
  return (
    <svg width={width} height={height} aria-hidden className="overflow-visible">
      <path d={d} fill="none" stroke="var(--faint)" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(last)} cy={y(values[last])} r={3} fill="var(--accent)" stroke="var(--surface)" strokeWidth={1.5} />
    </svg>
  );
}

export function StatTile({ label, value, delta, deltaGood, trend, hint }: { label: string; value: string; delta?: string | null; deltaGood?: boolean | null; trend?: number[]; hint?: string }) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-3.5">
      <div className="text-[12.5px] text-muted">{label}</div>
      <div className="mt-1 flex items-end justify-between gap-2">
        <div>
          <div className="text-2xl font-semibold tracking-tight">{value}</div>
          {delta && (
            <div className={cx("text-[12px] font-medium", deltaGood == null ? "text-muted" : deltaGood ? "text-ok" : "text-bad")}>{delta}</div>
          )}
          {hint && !delta && <div className="text-[12px] text-muted">{hint}</div>}
        </div>
        {trend && trend.length > 1 && <Sparkline values={trend} />}
      </div>
    </div>
  );
}

/** Horizontal share bars with a tick at the target share (one series: one color). */
export function ShareBars({ rows, color }: { rows: Array<{ label: string; share: number; target: number; detail?: string }>; color: string }) {
  return (
    <ul className="space-y-2.5">
      {rows.map((r) => (
        <li key={r.label}>
          <div className="mb-1 flex items-baseline justify-between gap-2 text-[12.5px]">
            <span>{r.label}</span>
            <span className="text-muted tabular-nums">
              {Math.round(r.share * 100)}% <span className="text-faint">· target {Math.round(r.target * 100)}%</span>
              {r.detail ? <span className="text-faint"> · {r.detail}</span> : null}
            </span>
          </div>
          <div className="relative h-2.5 rounded-full bg-surface-3" role="img" aria-label={`${r.label}: ${Math.round(r.share * 100)}% of cards, target ${Math.round(r.target * 100)}%`}>
            <div className="h-full rounded-full" style={{ width: `${Math.min(100, r.share * 100)}%`, background: color }} />
            <span className="absolute -top-0.5 h-3.5 w-0.5 rounded bg-text" style={{ left: `calc(${Math.min(100, r.target * 100)}% - 1px)` }} aria-hidden />
          </div>
        </li>
      ))}
    </ul>
  );
}

/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
// Interactive view of the hvx report data (hvx.reporting JSON): building figures, a sortable
// room table and, for the chosen room, when and how often the limits are exceeded.
import * as React from "react";
import { ArrowDown, ArrowUp, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import type { Label, Rating, ReportData, ReportRoom } from "@/lib/engine";
import { formatNumber, STRINGS, type Lang } from "@/lib/i18n";
import { color, DOMAINS, ink, LETTER } from "@/lib/tail";

const RATINGS = ["I", "II", "III", "IV"] as const;

export function Chip({ rating, size = "md", title }: { rating?: string | null; size?: "sm" | "md" | "lg"; title?: string }) {
  const cls = size === "lg" ? "min-w-12 text-[22px] leading-10 px-2.5" : size === "sm" ? "min-w-7 text-[12px] leading-5 px-1.5" : "min-w-9 text-[13px] leading-6 px-2";
  return (
    <span title={title} className={`inline-flex justify-center rounded-sm font-display font-bold tabular ${cls}`}
      style={{ background: color(rating as Rating), color: ink(rating as Rating) }}>
      {rating ?? "–"}
    </span>
  );
}

function Stat({ label, children, note }: { label: string; children: React.ReactNode; note?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-md border border-line bg-card p-5">
      <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{label}</div>
      <div className="flex items-baseline gap-2 font-display text-[32px] font-bold leading-10 tracking-[-0.02em] tabular">{children}</div>
      {note && <div className="text-[13px] text-muted-foreground">{note}</div>}
    </div>
  );
}

/** One stacked bar: how many rooms have each rating. */
function Mix({ title, counts, lang }: { title: string; counts: Record<string, number>; lang: Lang }) {
  const total = RATINGS.reduce((n, r) => n + (counts[r] ?? 0), 0);
  return (
    <div className="flex flex-col gap-2">
      <div className="text-[14px] font-semibold">{title}</div>
      <div className="flex h-7 w-full overflow-hidden rounded-sm border border-line bg-sunken" role="img"
        aria-label={`${title}: ${RATINGS.map((r) => `${r} ${counts[r] ?? 0}`).join(", ")}`}>
        {total > 0 && RATINGS.map((r) => (counts[r] ?? 0) > 0 && (
          <div key={r} className="flex items-center justify-center font-display text-[12px] font-bold" title={`${r}: ${counts[r]}`}
            style={{ width: `${(100 * counts[r]) / total}%`, background: color(r), color: ink(r) }}>
            {(counts[r] / total) >= 0.08 ? r : ""}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[12px] text-muted-foreground tabular">
        {RATINGS.map((r) => <span key={r}><span className="mr-1.5 inline-block size-2.5 rounded-[1px] align-middle" style={{ background: color(r) }} />{r} {formatNumber(counts[r] ?? 0, lang)}</span>)}
      </div>
    </div>
  );
}

/** Small vertical bar chart (values 0..max), blueprint bars on hairline gridlines. */
function Bars({ title, data, unit, max, lang }: { title: string; data: { key: string; label: string; value: number | null }[]; unit: string; max?: number; lang: Lang }) {
  const W = 360, H = 120, padL = 30, padB = 18, padT = 6;
  // a round top value, so the gridlines read 0, half and top in whole numbers
  const nice = (v: number) => [2, 4, 10, 20, 40, 50, 100, 200, 400, 500, 1000, 2000, 5000].find((n) => n >= v) ?? Math.ceil(v / 1000) * 1000;
  const top = max ?? nice(Math.max(0, ...data.map((d) => d.value ?? 0)));
  const step = (W - padL) / Math.max(1, data.length);
  const y = (v: number) => padT + (H - padT - padB) * (1 - v / top);
  const ticks = [0, top / 2, top];
  return (
    <figure className="m-0 flex min-w-0 flex-col gap-2">
      <figcaption className="text-[13px] font-semibold">{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img"
        aria-label={`${title}: ${data.filter((d) => d.value != null).map((d) => `${d.label} ${formatNumber(d.value!, lang, 0)} ${unit}`).join(", ")}`}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={padL} x2={W} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeWidth={1} />
            <text x={padL - 5} y={y(v)} textAnchor="end" dominantBaseline="central" fontSize={9} fill="var(--ink-muted)" fontFamily="JetBrains Mono">
              {formatNumber(v, lang, 0)}
            </text>
          </g>
        ))}
        {data.map((d, i) => {
          const x = padL + i * step + step * 0.15;
          const w = step * 0.7;
          const show = data.length <= 12 || i % 3 === 0;
          return (
            <g key={d.key}>
              {d.value != null && d.value > 0 && (
                <rect x={x} y={y(d.value)} width={w} height={Math.max(0.5, y(0) - y(d.value))} fill="var(--blueprint)" rx={1}>
                  <title>{`${d.label}: ${formatNumber(d.value, lang, 1)} ${unit}`}</title>
                </rect>
              )}
              {show && <text x={x + w / 2} y={H - 4} textAnchor="middle" fontSize={9} fill="var(--ink-muted)" fontFamily="JetBrains Mono">{d.label}</text>}
            </g>
          );
        })}
        <line x1={padL} x2={W} y1={y(0)} y2={y(0)} stroke="var(--ink)" strokeWidth={1} />
      </svg>
    </figure>
  );
}

type SortKey = "name" | "category" | "tail" | "co2" | "hot" | "score";

export function Dashboard({ data, building, lang }: { data: ReportData; building: Label | null; lang: Lang }) {
  const t = STRINGS[lang];
  const rooms = data.rooms.filter((r) => r.status === "ok");
  const [query, setQuery] = React.useState("");
  const [sort, setSort] = React.useState<{ key: SortKey; desc: boolean }>({ key: "co2", desc: true });
  const worst = [...rooms].sort((a, b) => (a.ieq_score ?? 101) - (b.ieq_score ?? 101))[0];
  const [selectedId, setSelectedId] = React.useState<string | undefined>(worst?.room_id);
  React.useEffect(() => { if (!rooms.some((r) => r.room_id === selectedId)) setSelectedId(worst?.room_id); }, [data]); // eslint-disable-line react-hooks/exhaustive-deps
  const selected = rooms.find((r) => r.room_id === selectedId);

  const rank = (r?: string | null) => (r ? RATINGS.indexOf(r as never) + 1 : 9);
  const value = (r: ReportRoom, key: SortKey): number | string => ({
    name: r.room_name.toLowerCase(), category: rank(r.achieved_category), tail: rank(r.tail_rating),
    co2: r.exceedance_hours["co2>1000"] ?? -1, hot: r.exceedance_hours["temperature>26"] ?? -1, score: r.ieq_score ?? -1,
  })[key];
  const shown = rooms
    .filter((r) => r.room_name.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => {
      const va = value(a, sort.key), vb = value(b, sort.key);
      const c = va < vb ? -1 : va > vb ? 1 : 0;
      return sort.desc ? -c : c;
    });
  const header = (key: SortKey, label: string, align = "text-left") => (
    <th scope="col" className={`py-2 pr-3 font-semibold ${align}`} aria-sort={sort.key === key ? (sort.desc ? "descending" : "ascending") : "none"}>
      <button type="button" className="inline-flex items-center gap-1 hover:text-foreground"
        onClick={() => setSort((s) => ({ key, desc: s.key === key ? !s.desc : key !== "name" }))}>
        {label}
        {sort.key === key && (sort.desc ? <ArrowDown className="size-3.5" aria-hidden /> : <ArrowUp className="size-3.5" aria-hidden />)}
      </button>
    </th>
  );
  const tailCounts: Record<string, number> = {};
  rooms.forEach((r) => { if (r.tail_rating) tailCounts[r.tail_rating] = (tailCounts[r.tail_rating] ?? 0) + 1; });
  const s = data.summary;
  const hours = (v?: number) => (v == null ? "–" : `${formatNumber(v, lang)} ${t.hoursUnitLong}`);

  return (
    <div className="flex flex-col gap-10">
      {/* building figures */}
      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(180px,1fr))]">
        <Stat label={t.kpiRooms}>{formatNumber(s.rooms_analysed, lang)}<span className="text-[18px] text-muted-foreground">/ {formatNumber(s.rooms_total, lang)}</span></Stat>
        <Stat label={t.kpiCategory} note={`${t.target} ${data.config.target_category}`}><Chip rating={s.category} size="lg" /></Stat>
        <Stat label={t.kpiTarget}>{s.meets_target_pct == null ? "–" : `${formatNumber(s.meets_target_pct, lang)} %`}</Stat>
        <Stat label={t.kpiScore}>{s.ieq_score == null ? "–" : formatNumber(s.ieq_score, lang, 0)}<span className="text-[18px] text-muted-foreground">/ 100</span></Stat>
        {building && (
          <Stat label={t.kpiTail}>
            <Chip rating={building.overall} size="lg" />
            <span className="flex gap-1">{DOMAINS.map((d) => <Chip key={d} rating={building.domains[d]} size="sm" title={`${t.domains[d]}: ${building.domains[d] ?? t.notMeasured}`} />)}</span>
          </Stat>
        )}
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Mix title={t.categoryMix} counts={s.category_counts} lang={lang} />
        <Mix title={t.tailMix} counts={tailCounts} lang={lang} />
      </div>

      {/* rooms */}
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-3">
          <div className="relative max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input aria-label={t.search} placeholder={t.search} value={query} onChange={(e) => setQuery(e.target.value)} className="pl-9" />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[14px] tabular">
              <thead>
                <tr className="border-b-2 border-foreground text-[13px] text-muted-foreground">
                  {header("name", t.room)}
                  {header("category", t.category)}
                  {header("tail", "TAIL")}
                  {header("co2", t.co2Hours, "text-right")}
                  {header("hot", t.hotHours, "text-right")}
                  {header("score", t.score, "text-right")}
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => {
                  const active = r.room_id === selectedId;
                  return (
                    <tr key={r.room_id} onClick={() => setSelectedId(r.room_id)} aria-selected={active}
                      className={`cursor-pointer border-b border-line transition-colors hover:bg-blueprint-soft ${active ? "bg-blueprint-soft" : ""}`}>
                      <td className="py-2 pr-3 font-semibold">
                        <button type="button" className="text-left hover:text-blueprint" onClick={() => setSelectedId(r.room_id)}>{r.room_name}</button>
                      </td>
                      <td className="py-2 pr-3"><Chip rating={r.achieved_category} size="sm" /></td>
                      <td className="py-2 pr-3"><Chip rating={r.tail_rating} size="sm" /></td>
                      <td className="py-2 pr-3 text-right font-mono text-[13px]">{hours(r.exceedance_hours["co2>1000"])}</td>
                      <td className="py-2 pr-3 text-right font-mono text-[13px]">{hours(r.exceedance_hours["temperature>26"])}</td>
                      <td className="py-2 text-right font-mono text-[13px]">{r.ieq_score == null ? "–" : formatNumber(r.ieq_score, lang)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* the chosen room */}
        <div className="min-w-0 rounded-md border border-line border-t-[3px] border-t-signal bg-card p-6">
          {!selected ? <p className="text-muted-foreground">{t.selectRoom}</p> : (
            <div className="flex flex-col gap-6">
              <div className="flex flex-col gap-2">
                <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{selected.occupancy}</div>
                <h3 className="m-0 font-display text-[22px] font-bold tracking-[-0.01em]">{selected.room_name}</h3>
                <div className="flex flex-wrap items-center gap-3 text-[13px] text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5">EN 16798-1 <Chip rating={selected.achieved_category} size="sm" /></span>
                  <span className="inline-flex items-center gap-1.5">TAIL <Chip rating={selected.tail_rating} size="sm" /></span>
                  <span className="inline-flex gap-1">{DOMAINS.map((d) => (
                    <span key={d} className="inline-flex items-center gap-0.5 font-mono text-[11px]" title={t.domains[d]}>{LETTER[d]}<Chip rating={selected.tail?.domains?.[d]} size="sm" /></span>
                  ))}</span>
                  {selected.br18_pass === false && <Badge tone="danger">BR18</Badge>}
                </div>
              </div>

              {selected.seasons.length > 0 && (
                <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
                  {selected.seasons.map((se) => (
                    <li key={se.season} className="flex items-center gap-2 rounded-sm border border-line px-2.5 py-1.5 text-[13px]">
                      {t.seasons[se.season] ?? se.season} <Chip rating={se.achieved_category} size="sm" />
                      <span className="font-mono text-[12px] text-muted-foreground">{formatNumber(se.compliance_pct, lang, 0)} %</span>
                      {se.adaptive && <Badge tone="info">{t.adaptive}</Badge>}
                    </li>
                  ))}
                </ul>
              )}

              <div className="grid gap-5 sm:grid-cols-2">
                {selected.profiles["co2>1000_pct_by_hour"] && (
                  <Bars title={t.byHour} unit="%" max={100} lang={lang}
                    data={Array.from({ length: 24 }, (_, h) => ({ key: String(h), label: String(h).padStart(2, "0"), value: selected.profiles["co2>1000_pct_by_hour"][String(h)] ?? null }))
                      .filter((d, i, all) => i >= all.findIndex((x) => x.value != null) && i <= all.length - 1 - [...all].reverse().findIndex((x) => x.value != null))} />
                )}
                {selected.profiles["co2>1000_pct_by_month"] && (
                  <Bars title={t.byMonth} unit="%" max={100} lang={lang}
                    data={Array.from({ length: 12 }, (_, m) => ({ key: String(m + 1), label: String(m + 1), value: selected.profiles["co2>1000_pct_by_month"][String(m + 1)] ?? null }))} />
                )}
                {selected.profiles["temperature>26_h_by_month"] && (
                  <Bars title={t.hotByMonth} unit={t.hoursUnitLong} lang={lang}
                    data={Array.from({ length: 12 }, (_, m) => ({ key: String(m + 1), label: String(m + 1), value: selected.profiles["temperature>26_h_by_month"][String(m + 1)] ?? null }))} />
                )}
              </div>

              <div className="overflow-x-auto">
                <div className="mb-2 text-[13px] font-semibold">{t.measured}</div>
                <table className="w-full text-[13px] tabular">
                  <thead>
                    <tr className="border-b border-foreground text-muted-foreground">
                      <th className="py-1.5 pr-3 text-left font-semibold">{t.parameter}</th>
                      <th className="py-1.5 pr-3 text-right font-semibold">{t.mean}</th>
                      <th className="py-1.5 pr-3 text-right font-semibold">{t.min}</th>
                      <th className="py-1.5 pr-3 text-right font-semibold">{t.max}</th>
                      <th className="py-1.5 text-right font-semibold">{t.compliance}</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono">
                    {Object.entries(selected.parameters).map(([k, p]) => (
                      <tr key={k} className="border-b border-line last:border-0">
                        <td className="py-1.5 pr-3 font-sans">{t.params[k] ?? k}</td>
                        <td className="py-1.5 pr-3 text-right">{formatNumber(p.mean, lang, k === "co2" ? 0 : 1)} <span className="text-muted-foreground">{p.unit}</span></td>
                        <td className="py-1.5 pr-3 text-right">{formatNumber(p.minimum, lang, k === "co2" ? 0 : 1)}</td>
                        <td className="py-1.5 pr-3 text-right">{formatNumber(p.maximum, lang, k === "co2" ? 0 : 1)}</td>
                        <td className="py-1.5 text-right">{formatNumber(p.compliance_pct, lang, 0)} %</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {selected.recommendations.length > 0 && (
                <div className="flex flex-col gap-3">
                  <div className="text-[13px] font-semibold">{t.recommendations}</div>
                  {selected.recommendations.map((rec, i) => (
                    <div key={i} className="flex flex-col gap-1 border-l-0 border-t border-line pt-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={rec.priority === "high" ? "danger" : rec.priority === "medium" ? "signal" : "neutral"}>{t.priority[rec.priority] ?? rec.priority}</Badge>
                        <span className="text-[14px] font-semibold">{rec.title}</span>
                      </div>
                      <p className="m-0 text-[13px] leading-5 text-muted-foreground">{rec.description}</p>
                      {rec.expected_benefit && <p className="m-0 text-[13px] leading-5">{rec.expected_benefit}</p>}
                    </div>
                  ))}
                </div>
              )}
              {selected.issues.length > 0 && (
                <details className="text-[13px]">
                  <summary className="cursor-pointer font-semibold">{t.issues} ({selected.issues.length})</summary>
                  <ul className="mt-2 flex list-disc flex-col gap-1 pl-5 text-muted-foreground">{selected.issues.map((x, i) => <li key={i}>{x}</li>)}</ul>
                </details>
              )}
            </div>
          )}
        </div>
      </div>

      {/* building actions */}
      <div className="flex flex-col gap-3">
        <h3 className="m-0 font-display text-[20px] font-medium">{t.actions}</h3>
        {data.actions.length === 0 ? <p className="text-muted-foreground">{t.noActions}</p> : (
          <ul className="m-0 grid list-none gap-4 p-0 [grid-template-columns:repeat(auto-fit,minmax(280px,1fr))]">
            {data.actions.map((a, i) => (
              <li key={i} className="flex flex-col gap-2 rounded-md border border-line bg-card p-5">
                <div className="flex items-center gap-2">
                  <Badge tone={a.priority === "high" ? "danger" : a.priority === "medium" ? "signal" : "neutral"}>{t.priority[a.priority] ?? a.priority}</Badge>
                  <span className="font-mono text-[12px] text-muted-foreground">{t.roomsCount(a.room_names.length)}</span>
                </div>
                <div className="font-display text-[17px] font-medium leading-6">{a.title}</div>
                <p className="m-0 text-[13px] leading-5 text-muted-foreground">{a.description}</p>
                <p className="m-0 text-[12px] leading-5 text-muted-foreground">{a.room_names.join(", ")}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

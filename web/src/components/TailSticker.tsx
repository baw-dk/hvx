/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
import * as React from "react";
import type { Domain, Label } from "@/lib/engine";
import { formatHours, formatNumber, STRINGS, type Lang } from "@/lib/i18n";
import { color, DOMAINS, ink, LETTER, MEMBERS, SCHOOL_ONLY } from "@/lib/tail";
import { stickerFontFaces } from "@/lib/fonts";

// BAW tokens used on the sticker (light theme: the sticker is printed)
const INK = "#10202E";
const MUTED = "#4A5864";
const LINE = "#D5D9D2";
const SIGNAL = "#F2B705";
const W = 420;
const H = 600;

const polar = (cx: number, cy: number, r: number, deg: number): [number, number] => {
  const rad = (deg * Math.PI) / 180;
  return [cx + r * Math.sin(rad), cy - r * Math.cos(rad)];
};
const pt = (p: [number, number]) => `${p[0].toFixed(2)},${p[1].toFixed(2)}`;

/** Annular sector with rounded corners (each corner a circle tangent to the edge and the arc). */
function sector(cx: number, cy: number, r0: number, r1: number, a0: number, a1: number, corner: number): string {
  const span = ((a1 - a0) * Math.PI) / 180;
  const c = Math.max(0, Math.min(corner, (r1 - r0) / 2 - 0.01, (r0 * span) / 2 * 0.95));
  const large = (deg: number) => (deg > 180 ? 1 : 0);
  if (c < 0.2) {
    return `M${pt(polar(cx, cy, r1, a0))} A${r1},${r1} 0 ${large(a1 - a0)} 1 ${pt(polar(cx, cy, r1, a1))} L${pt(polar(cx, cy, r0, a1))} A${r0},${r0} 0 ${large(a1 - a0)} 0 ${pt(polar(cx, cy, r0, a0))} Z`;
  }
  const to = (Math.asin(c / (r1 - c)) * 180) / Math.PI;
  const ti = (Math.asin(c / (r0 + c)) * 180) / Math.PI;
  const dOut = Math.sqrt((r1 - c) ** 2 - c ** 2);
  const dIn = Math.sqrt((r0 + c) ** 2 - c ** 2);
  return [
    `M${pt(polar(cx, cy, dOut, a0))}`,
    `A${c},${c} 0 0 1 ${pt(polar(cx, cy, r1, a0 + to))}`,
    `A${r1},${r1} 0 ${large(a1 - a0 - 2 * to)} 1 ${pt(polar(cx, cy, r1, a1 - to))}`,
    `A${c},${c} 0 0 1 ${pt(polar(cx, cy, dOut, a1))}`,
    `L${pt(polar(cx, cy, dIn, a1))}`,
    `A${c},${c} 0 0 1 ${pt(polar(cx, cy, r0, a1 - ti))}`,
    `A${r0},${r0} 0 ${large(a1 - a0 - 2 * ti)} 0 ${pt(polar(cx, cy, r0, a0 + ti))}`,
    `A${c},${c} 0 0 1 ${pt(polar(cx, cy, dIn, a0))} Z`,
  ].join(" ");
}

/** Arc for text: clockwise on the top half, reversed on the bottom half so text stays upright. */
function textArc(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const mid = ((a0 + a1) / 2) % 360;
  const large = a1 - a0 > 180 ? 1 : 0;
  if (mid > 90 && mid < 270) return `M${pt(polar(cx, cy, r, a1))} A${r},${r} 0 ${large} 0 ${pt(polar(cx, cy, r, a0))}`;
  return `M${pt(polar(cx, cy, r, a0))} A${r},${r} 0 ${large} 1 ${pt(polar(cx, cy, r, a1))}`;
}

// TAIL paper Fig. 1 positions: T top-left, A top-right, L bottom-right, I bottom-left
const QUADRANT: Record<Domain, number> = { acoustic: 0, luminous: 90, iaq: 180, thermal: 270 };

function Donut({ label, lang, cx, cy, R, uid }: { label: Label; lang: Lang; cx: number; cy: number; R: number; uid: string }) {
  const t = STRINGS[lang];
  const gap = 3.2;
  const rCore = R * 0.3;
  const rDom0 = rCore + gap;
  const rDom1 = R * 0.62;
  const rPar0 = rDom1 + gap;
  const pad = (r: number) => ((gap / r) * 180) / Math.PI / 2;
  const defs: React.ReactNode[] = [];
  const parts: React.ReactNode[] = [];
  for (const domain of DOMAINS) {
    const start = QUADRANT[domain];
    const members = MEMBERS[domain].filter((p) => label.profile === "school" || !SCHOOL_ONLY.has(p));
    const measured = members.filter((p) => label.parameters[p]);
    const missing = members.filter((p) => !label.parameters[p]);
    const segments = measured.map((p) => ({ key: p, full: t.params[p] ?? p, short: t.short[p] ?? p, rating: label.parameters[p].rating,
      tip: `${t.params[p] ?? p}: ${label.parameters[p].rating}` }));
    if (missing.length) {
      const one = missing.length === 1;
      segments.push({ key: `na-${domain}`, full: one ? (t.params[missing[0]] ?? missing[0]) : t.notMeasured, short: one ? (t.short[missing[0]] ?? "–") : "–",
        rating: undefined as never, tip: `${t.notMeasured}: ${missing.map((m) => t.params[m] ?? m).join(", ")}` });
    }
    const span = 90 / segments.length;
    const pPad = pad((rPar0 + R) / 2);
    const rText = (rPar0 + R) / 2;
    segments.forEach((seg, i) => {
      const a0 = start + i * span + pPad;
      const a1 = start + (i + 1) * span - pPad;
      parts.push(
        <path key={`p-${seg.key}`} d={sector(cx, cy, rPar0, R, a0, a1, 5)} fill={color(seg.rating)}>
          <title>{seg.tip}</title>
        </path>,
      );
      // label along the arc: the full name when it fits, else the short one (full name in the tooltip)
      const arcLength = (((a1 - a0) * Math.PI) / 180) * rText - 10;
      const fits = (text: string, size: number) => text.length * size * 0.56 <= arcLength;
      const text = fits(seg.full, 11) ? seg.full : fits(seg.short, 11) ? seg.short : null;
      if (!text) return;
      const id = `${uid}-${seg.key}`;
      defs.push(<path key={id} id={id} d={textArc(cx, cy, rText, a0, a1)} fill="none" />);
      parts.push(
        <text key={`t-${seg.key}`} fontSize={11} fontWeight={500} fill={ink(seg.rating)} dominantBaseline="central" fontFamily="Inter">
          <textPath href={`#${id}`} startOffset="50%" textAnchor="middle">{text}</textPath>
        </text>,
      );
    });
    const rating = label.domains[domain];
    const dPad = pad((rDom0 + rDom1) / 2);
    parts.push(
      <path key={`d-${domain}`} d={sector(cx, cy, rDom0, rDom1, start + dPad, start + 90 - dPad, 5)} fill={color(rating)}>
        <title>{`${t.domains[domain]}: ${rating ?? t.notMeasured}`}</title>
      </path>,
    );
    const id = `${uid}-dom-${domain}`;
    defs.push(<path key={id} id={id} d={textArc(cx, cy, (rDom0 + rDom1) / 2, start + dPad, start + 90 - dPad)} fill="none" />);
    parts.push(
      <text key={`dt-${domain}`} fontSize={12.5} fontWeight={700} fill={ink(rating)} dominantBaseline="central" fontFamily="Space Grotesk">
        <textPath href={`#${id}`} startOffset="50%" textAnchor="middle">{`${LETTER[domain]} · ${rating ?? "–"}`}</textPath>
      </text>,
    );
  }
  const overall = label.overall;
  return (
    <g>
      <defs>{defs}</defs>
      {parts}
      <circle cx={cx} cy={cy} r={rCore} fill={color(overall)} />
      <text x={cx} y={cy - rCore * 0.4} textAnchor="middle" dominantBaseline="central" fontSize={8.5} fontWeight={600} letterSpacing="0.08em" fill={ink(overall)} fontFamily="Inter">
        {t.overall.toUpperCase()}
      </text>
      <text x={cx} y={cy + rCore * 0.14} textAnchor="middle" dominantBaseline="central" fontSize={34} fontWeight={700} fill={ink(overall)} fontFamily="Space Grotesk">
        {overall ?? "–"}
      </text>
    </g>
  );
}

/** Dimension rule (BAW signature): 2 px ink line, end markers, 45° signal ticks; label in mono. */
function DimensionRule({ x0, x1, y, label }: { x0: number; x1: number; y: number; label?: string }) {
  const tick = (x: number) => (
    <g key={x}>
      <line x1={x} y1={y - 8} x2={x} y2={y + 8} stroke={INK} strokeWidth={2} />
      <line x1={x - 4} y1={y + 4} x2={x + 4} y2={y - 4} stroke={SIGNAL} strokeWidth={3} strokeLinecap="round" />
    </g>
  );
  const mid = (x0 + x1) / 2;
  const half = label ? label.length * 3.4 + 10 : 0;
  return (
    <g>
      <line x1={x0} y1={y} x2={label ? mid - half : x1} y2={y} stroke={INK} strokeWidth={2} />
      {label && <line x1={mid + half} y1={y} x2={x1} y2={y} stroke={INK} strokeWidth={2} />}
      {label && (
        <text x={mid} y={y} textAnchor="middle" dominantBaseline="central" fontSize={10.5} fontWeight={500} letterSpacing="0.04em" fill={MUTED} fontFamily="JetBrains Mono">
          {label}
        </text>
      )}
      {tick(x0)}
      {tick(x1)}
    </g>
  );
}

export const TailSticker = React.forwardRef<SVGSVGElement, { label: Label; lang: Lang; embedFonts?: boolean }>(({ label, lang, embedFonts = true }, ref) => {
  const t = STRINGS[lang];
  const uid = React.useId().replace(/[^a-zA-Z0-9]/g, "");
  const start = label.coverage.start?.slice(0, 10) ?? "";
  const end = label.coverage.end?.slice(0, 10) ?? "";
  const days = Math.round(label.coverage.days);
  const hours = formatNumber(label.occupied.hours, lang);
  const pad = 28;
  return (
    <svg ref={ref} xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img"
      aria-label={`TAIL ${label.overall ?? "–"}`} className="h-auto w-full max-w-[420px]">
      {embedFonts && <style>{stickerFontFaces()}</style>}
      <rect x={1} y={1} width={W - 2} height={H - 2} rx={4} fill="#FFFFFF" stroke={INK} strokeWidth={2} />

      {/* header: baw mark on its dimension rule, title right */}
      <text x={pad} y={58} fontSize={38} fontWeight={700} letterSpacing="-0.03em" fill={INK} fontFamily="Space Grotesk">baw</text>
      <DimensionRule x0={pad + 3} x1={pad + 78} y={74} />
      <text x={W - pad} y={40} textAnchor="end" fontSize={9.5} fontWeight={600} letterSpacing="0.08em" fill={MUTED} fontFamily="Inter">
        {t.eyebrow.toUpperCase()}
      </text>
      <text x={W - pad} y={70} textAnchor="end" fontSize={30} fontWeight={700} letterSpacing="-0.02em" fill={INK} fontFamily="Space Grotesk">TAIL</text>
      <line x1={pad} y1={98} x2={W - pad} y2={98} stroke={LINE} strokeWidth={1} />

      <Donut label={label} lang={lang} cx={W / 2} cy={248} R={132} uid={uid} />

      {/* the four domains */}
      {DOMAINS.map((d, i) => {
        const x = pad + (i % 2) * ((W - 2 * pad) / 2);
        const y = 410 + Math.floor(i / 2) * 34;
        const r = label.domains[d];
        return (
          <g key={d}>
            <rect x={x} y={y} width={26} height={26} rx={2} fill={color(r)} />
            <text x={x + 13} y={y + 13.5} textAnchor="middle" dominantBaseline="central" fontSize={13} fontWeight={700} fill={ink(r)} fontFamily="Space Grotesk">{LETTER[d]}</text>
            <text x={x + 36} y={y + 13.5} dominantBaseline="central" fontSize={13} fontWeight={500} fill={INK} fontFamily="Inter">{t.domains[d]}</text>
            <text x={x + (W - 2 * pad) / 2 - 14} y={y + 13.5} textAnchor="end" dominantBaseline="central" fontSize={14} fontWeight={700} fill={r ? INK : MUTED} fontFamily="Space Grotesk">
              {r ?? "–"}
            </text>
          </g>
        );
      })}

      {/* measured period on the dimension rule (the one signal on the label) */}
      <DimensionRule x0={pad + 4} x1={W - pad - 4} y={498} label={`${start} – ${end} · ${days} ${t.days}`} />

      {/* footer */}
      <text x={pad} y={536} fontSize={14} fontWeight={700} fill={INK} fontFamily="Space Grotesk">
        {(label.name || t.labelTitle).slice(0, 44)}
      </text>
      <text x={pad} y={555} fontSize={10.5} fill={MUTED} fontFamily="Inter">{t.profiles[label.profile]}</text>
      <text x={pad} y={571} fontSize={10.5} fill={MUTED} fontFamily="Inter">
        {`${formatHours(label.occupied, lang)} · ${hours} ${t.hoursUnit} ${t.assessed}`}
      </text>
      <text x={W - pad} y={571} textAnchor="end" fontSize={9} fontWeight={500} letterSpacing="0.04em" fill={MUTED} fontFamily="JetBrains Mono">
        hvx · CVR 46539214
      </text>
    </svg>
  );
});
TailSticker.displayName = "TailSticker";

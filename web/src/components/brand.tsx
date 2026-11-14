/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
// The BAW logo and dimension rule, as on the BAW website (components/brand.tsx there).

function Tick({ size, mono }: { size: number; mono?: boolean }) {
  const c = size / 2;
  const t = size * 0.22;
  return (
    <svg width={Math.round(size / 2)} height={size} viewBox={`0 0 ${size / 2} ${size}`} aria-hidden="true" className="block flex-none overflow-visible">
      <line x1={size / 4} y1={0} x2={size / 4} y2={size} strokeWidth={2} stroke="currentColor" />
      <line x1={size / 4 - t} y1={c + t} x2={size / 4 + t} y2={c - t} strokeWidth={3} strokeLinecap="round" stroke={mono ? "currentColor" : "var(--signal)"} />
    </svg>
  );
}

/** Architectural dimension line: extension ticks with a signal-yellow slash at each end. */
export function DimensionRule({ size = 24, mono }: { size?: number; mono?: boolean }) {
  const half = Math.round(size / 4);
  return (
    <div className="flex w-full items-center" aria-hidden="true">
      <Tick size={size} mono={mono} />
      <div className="h-0.5 flex-1 bg-current" style={{ marginLeft: -half, marginRight: -half }} />
      <Tick size={size} mono={mono} />
    </div>
  );
}

export function Logo({ size = 28, rule = true, mono = false }: { size?: number; rule?: boolean; mono?: boolean }) {
  return (
    <div className="inline-flex w-max flex-col items-stretch" role="img" aria-label="BAW">
      <span className="text-center font-display font-bold leading-[0.95] tracking-[-0.03em]" style={{ fontSize: size }} aria-hidden="true">baw</span>
      {rule && (
        <div style={{ marginTop: Math.round(size * 0.08), padding: `0 ${Math.round(size * 0.04)}px` }} aria-hidden="true">
          <DimensionRule size={Math.max(12, Math.round(size * 0.22))} mono={mono} />
        </div>
      )}
    </div>
  );
}

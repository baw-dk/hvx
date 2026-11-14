/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
import * as React from "react";
import { CalendarPlus, ChevronDown, Copy, Plus, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import type { Schedule, SchedulePeriod } from "@/lib/engine";
import { formatHours, formatNumber, STRINGS, type Lang } from "@/lib/i18n";

/** The schedule as the engine takes it, plus holiday names kept for the editor (ignored by hvx). */
export type EditableSchedule = Schedule & { holiday_names?: string[] };

const minutes = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + (m || 0);
};

export function weeklyHours(s: Schedule): number {
  return s.periods.reduce((sum, p) => {
    const a = minutes(p.start), b = minutes(p.end);
    return sum + (a <= b ? b - a : 1440 - a + b) / 60;
  }, 0);
}

/** Weekdays grouped by identical hours (as hvx's OccupancySchedule.day_groups). */
export function dayGroups(s: Schedule): { days: number[]; hours: [string, string][] }[] {
  const byDay = new Map<number, [string, string][]>();
  [...s.periods].sort((a, b) => a.day - b.day || minutes(a.start) - minutes(b.start))
    .forEach((p) => byDay.set(p.day, [...(byDay.get(p.day) ?? []), [p.start, p.end]]));
  const groups: { days: number[]; hours: [string, string][] }[] = [];
  [...byDay.keys()].sort((a, b) => a - b).forEach((day) => {
    const hours = byDay.get(day)!;
    const last = groups[groups.length - 1];
    if (last && JSON.stringify(last.hours) === JSON.stringify(hours) && last.days[last.days.length - 1] === day - 1) last.days.push(day);
    else groups.push({ days: [day], hours });
  });
  return groups;
}

export function simpleSchedule(start: string, end: string, weekdays: number[], publicHolidays: boolean): EditableSchedule {
  return { periods: weekdays.map((day) => ({ day, start, end })), holiday_periods: [], holiday_names: [], closed_days: [], public_holidays: publicHolidays };
}

export function ScheduleEditor({ value, onChange, profile, lang, years, loadHolidays, disabled }: {
  value: EditableSchedule;
  onChange: (s: EditableSchedule) => void;
  profile: EditableSchedule;
  lang: Lang;
  years: number[];
  loadHolidays: (years: number[]) => Promise<{ name: string; first: string; last: string }[]>;
  disabled?: boolean;
}) {
  const t = STRINGS[lang];
  const set = (patch: Partial<EditableSchedule>) => onChange({ ...value, ...patch });
  const periodsOf = (day: number) => value.periods.map((p, i) => ({ p, i })).filter(({ p }) => p.day === day)
    .sort((a, b) => minutes(a.p.start) - minutes(b.p.start));
  const setPeriod = (i: number, patch: Partial<SchedulePeriod>) =>
    set({ periods: value.periods.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const removePeriod = (i: number) => set({ periods: value.periods.filter((_, j) => j !== i) });
  const addPeriod = (day: number) => {
    const existing = periodsOf(day).map(({ p }) => p);
    const last = existing[existing.length - 1];
    // after the last period, with a 30-minute gap (a break), two hours long
    const hhmm = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
    const from = last ? Math.min(minutes(last.end) + 30, 23 * 60) : 8 * 60;
    const start = hhmm(from);
    const end = hhmm(Math.min(from + 120, 23 * 60 + 59));
    set({ periods: [...value.periods, { day, start, end }] });
  };
  const toggleDay = (day: number, open: boolean) => {
    if (open) {
      const template = periodsOf(0).length ? periodsOf(0).map(({ p }) => p) : [{ day, start: "08:00", end: "16:00" }];
      set({ periods: [...value.periods, ...template.map((p) => ({ ...p, day }))] });
    } else {
      set({ periods: value.periods.filter((p) => p.day !== day) });
    }
  };
  const copyMonday = () => {
    const monday = periodsOf(0).map(({ p }) => p);
    set({ periods: [...value.periods.filter((p) => p.day === 0 || p.day > 4), ...[1, 2, 3, 4].flatMap((day) => monday.map((p) => ({ ...p, day })))] });
  };
  const names = value.holiday_names ?? [];
  const setHoliday = (i: number, which: 0 | 1, date: string) =>
    set({ holiday_periods: value.holiday_periods.map((h, j) => (j === i ? (which === 0 ? [date, h[1]] : [h[0], date]) : h)) as [string, string][] });
  const removeHoliday = (i: number) => set({
    holiday_periods: value.holiday_periods.filter((_, j) => j !== i), holiday_names: names.filter((_, j) => j !== i),
  });
  const addSchoolHolidays = async () => {
    const list = await loadHolidays(years.length ? years : [new Date().getFullYear()]);
    const have = new Set(value.holiday_periods.map((h) => h.join("/")));
    const fresh = list.filter((h) => !have.has(`${h.first}/${h.last}`));
    set({
      holiday_periods: [...value.holiday_periods, ...fresh.map((h) => [h.first, h.last] as [string, string])],
      holiday_names: [...names, ...fresh.map((h) => h.name)],
    });
  };
  const changed = JSON.stringify({ ...value, holiday_names: undefined }) !== JSON.stringify({ ...profile, holiday_names: undefined });

  const summary = formatHours({ groups: dayGroups(value) }, lang) || t.closed;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <Label>{t.hours}</Label>
        <span className="font-mono text-[12px] text-muted-foreground tabular">
          {formatNumber(weeklyHours(value), lang, Number.isInteger(weeklyHours(value)) ? 0 : 1)} {t.perWeek}
          {value.holiday_periods.length ? ` · ${value.holiday_periods.length} ${t.holidays.toLowerCase()}` : ""}
          {value.closed_days.length ? ` · ${value.closed_days.length} ${t.closed.toLowerCase()}` : ""}
        </span>
      </div>
      <p className="rounded-sm border border-line bg-sunken px-3 py-2 font-mono text-[13px] leading-5">{summary}</p>

      <Collapsible>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <CollapsibleTrigger disabled={disabled} className="group inline-flex items-center gap-1 text-[14px] font-semibold text-blueprint disabled:text-muted-foreground">
            {t.advanced} <ChevronDown className="size-4 transition-transform group-data-[state=open]:rotate-180" aria-hidden />
          </CollapsibleTrigger>
          {changed && (
            <button type="button" className="inline-flex items-center gap-1 text-[13px] text-muted-foreground hover:text-foreground" onClick={() => onChange(profile)} disabled={disabled}>
              <RotateCcw className="size-3.5" aria-hidden /> {t.resetSchedule}
            </button>
          )}
        </div>
        <CollapsibleContent className="mt-4 flex flex-col gap-6">
          {/* week */}
          <div className="flex flex-col">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{t.schedule}</span>
              <Button size="sm" variant="ghost" onClick={copyMonday} disabled={disabled || !periodsOf(0).length}><Copy aria-hidden /> {t.copyMonday}</Button>
            </div>
            <ul className="flex flex-col border-t-2 border-foreground">
              {t.dayNamesLong.map((dayName, day) => {
                const items = periodsOf(day);
                return (
                  <li key={day} className="grid grid-cols-[minmax(0,7.5rem)_auto_minmax(0,1fr)] items-start gap-3 border-b border-line py-2.5 max-sm:grid-cols-[minmax(0,1fr)_auto]">
                    <span className="pt-2 text-[14px] font-medium capitalize">{dayName}</span>
                    <Switch aria-label={dayName} checked={items.length > 0} onCheckedChange={(on) => toggleDay(day, on)} disabled={disabled} className="mt-2" />
                    <div className="flex flex-wrap items-center gap-2 max-sm:col-span-2">
                      {items.length === 0 && <span className="pt-1 text-[13px] text-muted-foreground">{t.closed}</span>}
                      {items.map(({ p, i }) => (
                        <span key={i} className="inline-flex items-center gap-1 rounded-sm border border-line bg-card p-1">
                          <Input aria-label={`${dayName} ${t.from}`} type="time" value={p.start} disabled={disabled} className="h-8 w-[6.5rem] border-0 px-1.5 font-mono text-[13px]"
                            onChange={(e) => e.target.value && setPeriod(i, { start: e.target.value })} />
                          <span className="text-muted-foreground">–</span>
                          <Input aria-label={`${dayName} ${t.to}`} type="time" value={p.end === "24:00" ? "23:59" : p.end} disabled={disabled} className="h-8 w-[6.5rem] border-0 px-1.5 font-mono text-[13px]"
                            onChange={(e) => e.target.value && setPeriod(i, { end: e.target.value })} />
                          <button type="button" aria-label={t.removePeriod} onClick={() => removePeriod(i)} disabled={disabled}
                            className="inline-flex size-7 items-center justify-center rounded-sm text-muted-foreground hover:bg-sunken hover:text-foreground">
                            <X className="size-3.5" aria-hidden />
                          </button>
                        </span>
                      ))}
                      {items.length > 0 && (
                        <Button size="sm" variant="ghost" onClick={() => addPeriod(day)} disabled={disabled} aria-label={`${t.addPeriod}: ${dayName}`}>
                          <Plus aria-hidden /> <span className="max-sm:sr-only">{t.addPeriod}</span>
                        </Button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="flex items-center justify-between gap-4">
            <Label htmlFor="public-holidays">{t.publicHolidays}</Label>
            <Switch id="public-holidays" checked={value.public_holidays} onCheckedChange={(on) => set({ public_holidays: on })} disabled={disabled} />
          </div>

          {/* holidays */}
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{t.holidays}</span>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="quiet" onClick={addSchoolHolidays} disabled={disabled}><CalendarPlus aria-hidden /> {t.schoolHolidays}</Button>
                <Button size="sm" variant="ghost" disabled={disabled} onClick={() => {
                  const y = years[0] ?? new Date().getFullYear();
                  set({ holiday_periods: [...value.holiday_periods, [`${y}-07-01`, `${y}-07-31`]], holiday_names: [...names, ""] });
                }}><Plus aria-hidden /> {t.addHoliday}</Button>
              </div>
            </div>
            {value.holiday_periods.length > 0 && (
              <ul className="flex flex-col gap-2">
                {value.holiday_periods.map(([first, last], i) => (
                  <li key={i} className="flex flex-wrap items-center gap-2">
                    <span className="w-20 truncate text-[13px] text-muted-foreground">{names[i] || "–"}</span>
                    <Input aria-label={t.first} type="date" value={first} disabled={disabled} className="h-8 w-[10rem] font-mono text-[13px]" onChange={(e) => e.target.value && setHoliday(i, 0, e.target.value)} />
                    <span className="text-muted-foreground">–</span>
                    <Input aria-label={t.last} type="date" value={last} min={first} disabled={disabled} className="h-8 w-[10rem] font-mono text-[13px]" onChange={(e) => e.target.value && setHoliday(i, 1, e.target.value)} />
                    <button type="button" aria-label={t.remove} onClick={() => removeHoliday(i)} disabled={disabled}
                      className="inline-flex size-8 items-center justify-center rounded-sm text-muted-foreground hover:bg-sunken hover:text-foreground">
                      <X className="size-4" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-[12px] leading-5 text-muted-foreground">{t.schoolHolidaysHint}</p>
          </div>

          {/* closed days */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{t.closedDays}</span>
              <Button size="sm" variant="ghost" disabled={disabled} onClick={() => set({ closed_days: [...value.closed_days, `${years[0] ?? new Date().getFullYear()}-05-01`] })}>
                <Plus aria-hidden /> {t.addClosedDay}
              </Button>
            </div>
            {value.closed_days.length > 0 && (
              <ul className="flex flex-wrap gap-2">
                {value.closed_days.map((d, i) => (
                  <li key={i} className="inline-flex items-center gap-1">
                    <Input aria-label={t.closedDays} type="date" value={d} disabled={disabled} className="h-8 w-[10rem] font-mono text-[13px]"
                      onChange={(e) => e.target.value && set({ closed_days: value.closed_days.map((x, j) => (j === i ? e.target.value : x)) })} />
                    <button type="button" aria-label={t.remove} onClick={() => set({ closed_days: value.closed_days.filter((_, j) => j !== i) })} disabled={disabled}
                      className="inline-flex size-8 items-center justify-center rounded-sm text-muted-foreground hover:bg-sunken hover:text-foreground">
                      <X className="size-4" aria-hidden />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
import EngineWorker from "@/engine.worker.ts?worker";

export type Rating = "I" | "II" | "III" | "IV";
export type Domain = "thermal" | "acoustic" | "iaq" | "luminous";

export interface ParameterResult {
  rating: Rating;
  domain: Domain;
  unit?: string | null;
  mean?: number | null;
  summary_value?: number | null;
  samples: number;
  rule?: string | null;
  adaptive?: boolean | null;
  distribution: Record<string, number>;
}

export interface SchedulePeriod { day: number; start: string; end: string }
export interface Schedule {
  periods: SchedulePeriod[];
  holiday_periods: [string, string][];
  closed_days: string[];
  public_holidays: boolean;
  always?: boolean;
}

export interface Label {
  kind?: "building";
  basis?: string;
  rooms?: { name?: string | null; overall: Rating | null; domains: Partial<Record<Domain, Rating>> }[];
  distribution?: Record<string, Record<string, number>>;
  name?: string | null;
  profile: "office" | "hotel" | "school";
  standard: string;
  overall: Rating | null;
  domains: Partial<Record<Domain, Rating>>;
  parameters: Record<string, ParameterResult>;
  not_rated: Record<string, string>;
  extensions: Record<string, Rating>;
  coverage: { start: string; end: string; days: number; step_minutes: number; samples: number; completeness_pct: Record<string, number> };
  occupied: { description: string; start: string; end: string; weekdays: number[]; all_hours: boolean; hours: number; samples: number;
    building_type: string; country: string; groups?: { days: number[]; hours: [string, string][] }[] };
  warnings: string[];
}

export interface RateOptions {
  building_type: "office" | "hotel" | "school";
  room_type?: string | null;
  occupied_from?: string;
  occupied_to?: string;
  mechanical_cooling?: boolean | null;
  volume_m3?: number | null;
  spot_values?: Record<string, number>;
  name?: string | null;
  country?: string;
  schedule?: Schedule | null;
}

export interface RoomInput {
  name: string;
  csv: string;
  columns?: Record<string, string>;
  volume_m3?: number | null;
  spot_values?: Record<string, number>;
}

export interface ReportOptions {
  building_name: string;
  building_type: RateOptions["building_type"];
  room_type?: string | null;
  mechanical_cooling?: boolean | null;
  language: "en" | "da";
  schedule?: Schedule | null;
}

export type Progress = "runtime" | "packages" | "hvx" | "report";

let worker: Worker | null = null;
let nextId = 1;
const pending = new Map<number, { resolve: (v: any) => void; reject: (e: Error) => void }>();
const listeners = new Set<(p: Progress) => void>();

function getWorker(): Worker {
  if (worker) return worker;
  worker = new EngineWorker();
  worker.onmessage = (event) => {
    const msg = event.data;
    if (msg.type === "progress") {
      listeners.forEach((l) => l(msg.step));
      return;
    }
    const p = pending.get(msg.id);
    if (!p) return;
    pending.delete(msg.id);
    msg.ok ? p.resolve(msg.result) : p.reject(new Error(msg.error));
  };
  return worker;
}

function call<T>(type: string, payload?: unknown): Promise<T> {
  const id = nextId++;
  return new Promise<T>((resolve, reject) => {
    pending.set(id, { resolve, reject });
    getWorker().postMessage({ id, type, payload });
  });
}

export const engine = {
  init: () => call<{ version: string }>("init"),
  detect: (csv: string) => call<Record<string, string | null>>("detect", { csv }),
  rate: (csv: string, options: RateOptions, columns?: Record<string, string>) => call<Label>("rate", { csv, options, columns }),
  labels: (rooms: RoomInput[], building_name: string | null, options: Omit<RateOptions, "name" | "volume_m3" | "spot_values">) =>
    call<{ rooms: Label[]; building: Label | null }>("labels", { rooms, building_name, options }),
  report: (rooms: RoomInput[], options: ReportOptions) => call<{ html: string; data: ReportData }>("report", { rooms, options }),
  holidays: (years: number[]) => call<{ name: string; first: string; last: string }[]>("holidays", { years }),
  hours: (building_type: string) => call<{ profile: string; start: string; end: string; weekdays: number[] }>("hours", { building_type }),
  onProgress: (fn: (p: Progress) => void) => {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
};

// The parts of the hvx report data (hvx.reporting, JSON renderer) the dashboard reads
export interface ReportRoom {
  room_id: string;
  room_name: string;
  status: string;
  achieved_category: string | null;
  meets_target: boolean | null;
  ieq_score: number | null;
  compliance: Record<string, number>;
  parameters: Record<string, { unit: string; compliance_pct: number; mean: number; minimum: number; maximum: number }>;
  seasons: { season: string; achieved_category: string | null; compliance_pct: number; adaptive: boolean; time_in_category_pct: Record<string, number> }[];
  tail_rating: string | null;
  tail: { overall: Rating | null; domains: Partial<Record<Domain, Rating>>; parameters: Record<string, Rating> };
  br18_pass: boolean | null;
  br18_failed: string[];
  occupancy: string;
  exceedance_hours: Record<string, number>;
  profiles: Record<string, Record<string, number>>;
  recommendations: { title: string; type: string; priority: string; description: string; expected_benefit?: string }[];
  issues: string[];
  warnings: string[];
  data_quality: { samples: number; start: string; end: string; completeness_pct: number };
}

export interface ReportData {
  config: { target_category: string; language: string; seasons: string[] };
  summary: { rooms_total: number; rooms_analysed: number; category: string | null; category_counts: Record<string, number>;
    meets_target_pct: number | null; ieq_score: number | null; compliance: Record<string, number>; exceedance_hours: Record<string, number> };
  rooms: ReportRoom[];
  actions: { type: string; title: string; priority: string; room_names: string[]; description: string; expected_benefit?: string }[];
  highlights: string[];
  warnings: string[];
}

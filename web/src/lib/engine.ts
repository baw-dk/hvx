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

export interface Label {
  name?: string | null;
  profile: "office" | "hotel" | "school";
  standard: string;
  overall: Rating | null;
  domains: Partial<Record<Domain, Rating>>;
  parameters: Record<string, ParameterResult>;
  not_rated: Record<string, string>;
  extensions: Record<string, Rating>;
  coverage: { start: string; end: string; days: number; step_minutes: number; samples: number; completeness_pct: Record<string, number> };
  occupied: { description: string; start: string; end: string; weekdays: number[]; all_hours: boolean; hours: number; samples: number; building_type: string; country: string };
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
}

export type Progress = "runtime" | "packages" | "hvx";

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
  hours: (building_type: string) => call<{ profile: string; start: string; end: string; weekdays: number[] }>("hours", { building_type }),
  onProgress: (fn: (p: Progress) => void) => {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
};

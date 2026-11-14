/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
// A synthetic school year (hourly, 2024) to try the app: no real building's data.

interface RoomTraits { seed: number; co2: number; warm: number; noise: number }

export function exampleCsv({ seed, co2, warm, noise }: RoomTraits = { seed: 42, co2: 1, warm: 0, noise: 0 }): string {
  let state = seed;
  const rand = () => ((state = (state * 1664525 + 1013904223) % 4294967296) / 4294967296);
  const jitter = (s: number) => (rand() - 0.5) * 2 * s;
  const rows = ["timestamp,temperature,co2,humidity,noise,outdoor_temperature"];
  const start = Date.UTC(2024, 0, 1);
  for (let h = 0; h < 366 * 24; h++) {
    const d = new Date(start + h * 3600_000);
    const day = Math.floor(h / 24);
    const hour = d.getUTCHours();
    const weekday = (d.getUTCDay() + 6) % 7;
    const summerHoliday = day >= 180 && day < 222;
    const occupied = weekday < 5 && hour >= 8 && hour < 15 && !summerHoliday;
    const season = Math.cos(((day - 200) / 366) * 2 * Math.PI); // 1 in July, -1 in January
    const outdoor = 9 + 8 * season + 4 * Math.sin(((hour - 9) / 24) * 2 * Math.PI) + jitter(2);
    const temp = 21.4 + 1.6 * Math.max(0, season) + (occupied ? 1.1 + warm : -0.4) + (0.5 + warm / 3) * Math.max(0, outdoor - 20) + jitter(0.4);
    const ppm = occupied ? 560 + 520 * co2 * Math.min(1, (hour - 7) / 4) * (0.7 + 0.6 * rand()) : 430 + jitter(15);
    const rh = 38 + 10 * season + jitter(4);
    const db = occupied ? 30 + noise + jitter(2) : 26 + jitter(1);
    const iso = d.toISOString().slice(0, 16).replace("T", " ");
    rows.push(`${iso},${temp.toFixed(1)},${Math.round(ppm)},${rh.toFixed(0)},${db.toFixed(0)},${outdoor.toFixed(1)}`);
  }
  return rows.join("\n") + "\n";
}

/** Four classrooms that behave differently: good, stuffy, warm, noisy and stuffy. */
export function exampleBuilding(lang: "en" | "da"): { name: string; file: string; csv: string }[] {
  const room = lang === "da" ? "Klasse" : "Classroom";
  const rooms: [string, RoomTraits][] = [
    ["1.01", { seed: 11, co2: 0.55, warm: 0, noise: 0 }],
    ["1.02", { seed: 23, co2: 1.15, warm: 0.2, noise: 1 }],
    ["2.01", { seed: 37, co2: 0.8, warm: 1.4, noise: 0 }],
    ["2.02", { seed: 51, co2: 1.45, warm: 0.6, noise: 9 }],
  ];
  return rooms.map(([no, traits]) => ({ name: `${room} ${no}`, file: `classroom-${no}-2024.csv`, csv: exampleCsv(traits) }));
}

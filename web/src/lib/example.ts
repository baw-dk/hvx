/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
// A synthetic classroom year (hourly, 2024) to try the app: no real building's data.
export function exampleCsv(): string {
  let seed = 42;
  const rand = () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);
  const noise = (s: number) => (rand() - 0.5) * 2 * s;
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
    const outdoor = 9 + 8 * season + 4 * Math.sin((hour - 9) / 24 * 2 * Math.PI) + noise(2);
    const temp = 21.6 + 1.6 * Math.max(0, season) + (occupied ? 1.2 : -0.4) + 0.5 * Math.max(0, outdoor - 20) + noise(0.4);
    const co2 = occupied ? 650 + 520 * Math.min(1, (hour - 7) / 4) * (0.7 + 0.6 * rand()) : 430 + noise(15);
    const rh = 38 + 10 * season + noise(4);
    const db = occupied ? 31 + noise(2) : 27 + noise(1);
    const iso = d.toISOString().slice(0, 16).replace("T", " ");
    rows.push(`${iso},${temp.toFixed(1)},${Math.round(co2)},${rh.toFixed(0)},${db.toFixed(0)},${outdoor.toFixed(1)}`);
  }
  return rows.join("\n") + "\n";
}

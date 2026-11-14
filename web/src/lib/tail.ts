/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
import type { Domain, Rating } from "./engine";

// TAIL scale (as in the hvx reports): I green ... IV red, grey = not measured
export const TAIL_COLORS: Record<string, string> = { I: "#5cc489", II: "#f4c84f", III: "#f39a4b", IV: "#e8605b", none: "#e3e6ea" };
export const TAIL_TEXT: Record<string, string> = { I: "#0f3d24", II: "#4a3700", III: "#4a2300", IV: "#ffffff", none: "#5b6472" };
export const color = (r?: Rating | null) => TAIL_COLORS[r ?? "none"];
export const ink = (r?: Rating | null) => TAIL_TEXT[r ?? "none"];

export const DOMAINS: Domain[] = ["thermal", "acoustic", "iaq", "luminous"];
export const LETTER: Record<Domain, string> = { thermal: "T", acoustic: "A", iaq: "I", luminous: "L" };
// TAIL parameters per domain (order of the outer ring)
export const MEMBERS: Record<Domain, string[]> = {
  thermal: ["temperature"],
  acoustic: ["noise", "reverberation_time"],
  iaq: ["co2", "relative_humidity", "pm25", "no2", "formaldehyde", "benzene", "radon", "ventilation", "mold"],
  luminous: ["illuminance", "daylight_factor"],
};
// school-only parameters are not offered for offices and hotels
export const SCHOOL_ONLY = new Set(["no2", "reverberation_time"]);

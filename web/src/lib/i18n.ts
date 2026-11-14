/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
export type Lang = "en" | "da";

const en = {
  eyebrow: "Indoor environment",
  title: "TAIL label from a year of measurements",
  lead: "Upload one CSV file with a year of indoor measurements. You get a TAIL rating of the thermal, acoustic, indoor-air and luminous environment, and a label to print or share.",
  privacy: "Your file stays in this browser. Nothing is uploaded.",
  step1: "Measurements", step2: "Building", step3: "Label",
  drop: "Drop a CSV file here, or choose one",
  dropHint: "One year (365 days) of measurements, one row per time stamp. Columns: time, then any of temperature, CO₂, humidity, noise, illuminance, PM2.5, NO₂. Outdoor temperature is optional.",
  choose: "Choose file", example: "Try an example year", rows: "rows",
  engineLoading: "Loading the rating engine", engineReady: "Rating engine ready",
  engineSteps: { runtime: "Python runtime", packages: "pandas and numpy", hvx: "hvx" },
  columns: "Columns found", columnHint: "Check what each column measures. Unused columns are ignored.",
  ignore: "Ignore", time: "Time", outdoor: "Outdoor temperature",
  buildingType: "Building type", office: "Office", hotel: "Hotel", school: "School",
  roomType: "Room type", smallOffice: "Small office", openOffice: "Open-plan office",
  name: "Name on the label", namePlaceholder: "e.g. North School, room 1.12",
  cooling: "Mechanical cooling", coolingHint: "Without cooling, summer temperatures are rated with the adaptive model. This needs an outdoor temperature column.",
  hours: "Assessed hours", from: "From", to: "To",
  more: "More measurements (optional)", volume: "Room volume", rt: "Reverberation time", df: "Daylight factor", radon: "Radon",
  create: "Create label", rating: "Rating…",
  labelTitle: "TAIL label", overall: "Overall",
  download: "Download", svg: "SVG", png: "PNG", startOver: "New file",
  parameters: "Parameters", parameter: "Parameter", value: "Value", ratingCol: "Rating", rule: "Rule",
  notRated: "Not rated", warnings: "Notes",
  domains: { thermal: "Thermal", acoustic: "Acoustic", iaq: "Indoor air", luminous: "Light" },
  params: {
    temperature: "Temperature", relative_humidity: "Relative humidity", co2: "CO₂", noise: "Noise", illuminance: "Illuminance",
    pm25: "PM2.5", no2: "NO₂", formaldehyde: "Formaldehyde", benzene: "Benzene", radon: "Radon", ventilation: "Ventilation",
    mold: "Mould", daylight_factor: "Daylight factor", reverberation_time: "Reverberation time",
  } as Record<string, string>,
  short: {
    temperature: "Temperature", relative_humidity: "RH", co2: "CO₂", noise: "Noise", illuminance: "Lux", pm25: "PM2.5",
    no2: "NO₂", formaldehyde: "HCHO", benzene: "Benzene", radon: "Radon", ventilation: "Vent.", mold: "Mould",
    daylight_factor: "DF", reverberation_time: "RT",
  } as Record<string, string>,
  profiles: { office: "Office · TAIL (Wargocki et al. 2021)", hotel: "Hotel · TAIL (Wargocki et al. 2021)", school: "School · TAIL for schools (Tran 2024)" },
  period: "Measured", assessed: "assessed", days: "d", hoursUnit: "h",
  notMeasured: "not measured", madeWith: "Rated with hvx",
  method: "How the rating works",
  methodText: "Each parameter is rated I (best) to IV over the assessed hours, a domain takes its worst parameter, and the overall rating its worst domain. Offices and hotels follow the TAIL scheme (Wargocki et al. 2021); schools follow the TAIL scheme for schools (Tran 2024), with classroom noise limits, NO₂ and reverberation time.",
  error: "Could not rate the file",
  footer: "baw · Bruno Adam Wallon · CVR 46539214 · Copenhagen",
  source: "Source code",
};
type Dict = typeof en;

const da: Dict = {
  eyebrow: "Indeklima",
  title: "TAIL-mærke ud fra et års målinger",
  lead: "Upload én CSV-fil med et års indeklimamålinger. Du får en TAIL-vurdering af det termiske, akustiske, luftkvaliteten og lysforholdene, og et mærke, du kan printe eller dele.",
  privacy: "Filen bliver i din browser. Intet uploades.",
  step1: "Målinger", step2: "Bygning", step3: "Mærke",
  drop: "Træk en CSV-fil hertil, eller vælg en",
  dropHint: "Et år (365 dage) med målinger, én række pr. tidspunkt. Kolonner: tid og en eller flere af temperatur, CO₂, fugtighed, støj, lys, PM2.5, NO₂. Udetemperatur er valgfri.",
  choose: "Vælg fil", example: "Prøv et eksempelår", rows: "rækker",
  engineLoading: "Indlæser beregningen", engineReady: "Beregningen er klar",
  engineSteps: { runtime: "Python", packages: "pandas og numpy", hvx: "hvx" },
  columns: "Fundne kolonner", columnHint: "Tjek, hvad hver kolonne måler. Kolonner uden valg springes over.",
  ignore: "Spring over", time: "Tid", outdoor: "Udetemperatur",
  buildingType: "Bygningstype", office: "Kontor", hotel: "Hotel", school: "Skole",
  roomType: "Rumtype", smallOffice: "Enkeltkontor", openOffice: "Storrumskontor",
  name: "Navn på mærket", namePlaceholder: "f.eks. Nordskolen, lokale 1.12",
  cooling: "Mekanisk køling", coolingHint: "Uden køling vurderes sommertemperaturen med den adaptive model. Det kræver en kolonne med udetemperatur.",
  hours: "Vurderet tid", from: "Fra", to: "Til",
  more: "Flere målinger (valgfrit)", volume: "Rumvolumen", rt: "Efterklangstid", df: "Dagslysfaktor", radon: "Radon",
  create: "Lav mærket", rating: "Beregner…",
  labelTitle: "TAIL-mærke", overall: "Samlet",
  download: "Hent", svg: "SVG", png: "PNG", startOver: "Ny fil",
  parameters: "Parametre", parameter: "Parameter", value: "Værdi", ratingCol: "Vurdering", rule: "Regel",
  notRated: "Ikke vurderet", warnings: "Bemærkninger",
  domains: { thermal: "Termisk", acoustic: "Akustik", iaq: "Luftkvalitet", luminous: "Lys" },
  params: {
    temperature: "Temperatur", relative_humidity: "Relativ fugtighed", co2: "CO₂", noise: "Støj", illuminance: "Belysningsstyrke",
    pm25: "PM2.5", no2: "NO₂", formaldehyde: "Formaldehyd", benzene: "Benzen", radon: "Radon", ventilation: "Ventilation",
    mold: "Skimmel", daylight_factor: "Dagslysfaktor", reverberation_time: "Efterklangstid",
  },
  short: {
    temperature: "Temperatur", relative_humidity: "RF", co2: "CO₂", noise: "Støj", illuminance: "Lux", pm25: "PM2.5",
    no2: "NO₂", formaldehyde: "HCHO", benzene: "Benzen", radon: "Radon", ventilation: "Vent.", mold: "Skimmel",
    daylight_factor: "DF", reverberation_time: "RT",
  },
  profiles: { office: "Kontor · TAIL (Wargocki m.fl. 2021)", hotel: "Hotel · TAIL (Wargocki m.fl. 2021)", school: "Skole · TAIL for skoler (Tran 2024)" },
  period: "Målt", assessed: "vurderet", days: "d", hoursUnit: "t",
  notMeasured: "ikke målt", madeWith: "Vurderet med hvx",
  method: "Sådan vurderes der",
  methodText: "Hver parameter vurderes fra I (bedst) til IV over den vurderede tid, et domæne får sin dårligste parameter og den samlede vurdering det dårligste domæne. Kontorer og hoteller følger TAIL (Wargocki m.fl. 2021); skoler følger TAIL for skoler (Tran 2024) med støjgrænser for klasselokaler, NO₂ og efterklangstid.",
  error: "Filen kunne ikke vurderes",
  footer: "baw · Bruno Adam Wallon · CVR 46539214 · København",
  source: "Kildekode",
};

export const STRINGS: Record<Lang, Dict> = { en, da };

export function formatNumber(value: number, lang: Lang, digits = 0): string {
  // BAW: thin space between thousands; Danish decimal comma
  const fixed = value.toFixed(digits);
  const [int, dec] = fixed.split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return dec ? `${grouped}${lang === "da" ? "," : "."}${dec}` : grouped;
}

const DAY_NAMES: Record<Lang, string[]> = {
  en: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
  da: ["man", "tir", "ons", "tor", "fre", "lør", "søn"],
};

/** "Mon–Fri 08:00–17:00" / "man–fre 08.00–17.00"; every day for hotels. */
export function formatHours(o: { start?: string; end?: string; weekdays?: number[]; all_hours?: boolean }, lang: Lang): string {
  if (o.all_hours) return lang === "da" ? "alle timer" : "all hours";
  const names = DAY_NAMES[lang];
  const days = o.weekdays ?? [];
  const contiguous = days.length > 1 && days.every((d, i) => i === 0 || d === days[i - 1] + 1);
  const dayText = days.length === 7 ? (lang === "da" ? "alle dage" : "every day")
    : contiguous ? `${names[days[0]]}–${names[days[days.length - 1]]}` : days.map((d) => names[d]).join(", ");
  const time = (s?: string) => (lang === "da" ? (s ?? "").replace(":", ".") : s ?? "");
  return `${dayText} ${time(o.start)}–${time(o.end)}`;
}

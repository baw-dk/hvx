/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
export type Lang = "en" | "da";

const en = {
  // page
  eyebrow: "Indoor environment",
  heroEyebrow: "Indoor environment · TAIL · EN 16798-1",
  title: "TAIL labels and a full report from your measurements",
  lead: "Upload one CSV file per room, with a year of measurements. You get a TAIL label for every room and for the building, the full indoor-climate report and an interactive dashboard.",
  privacy: "Your files stay in this browser. Nothing is uploaded.",
  nav: { labels: "Labels", report: "Report", dashboard: "Dashboard", contact: "Get in touch" },
  langLabel: "Language",

  // 01 rooms
  step1: "Rooms",
  drop: "Drop CSV files here, one per room",
  dropHint: "A year (365 days) of measurements per room, one row per time stamp. Columns: time, then any of temperature, CO₂, humidity, noise, illuminance, PM2.5, NO₂. Outdoor temperature is optional.",
  choose: "Choose files", addRooms: "Add rooms", example: "Try an example building", rows: "rows",
  room: "Room", file: "File", remove: "Remove", details: "Columns and room data",
  roomsCount: (n: number) => (n === 1 ? "1 room" : `${n} rooms`),
  buildingName: "Building name", buildingPlaceholder: "e.g. North School",
  engineLoading: "Loading the rating engine", engineReady: "Rating engine ready",
  engineSteps: { runtime: "Python runtime", packages: "pandas and numpy", hvx: "hvx", report: "report engine" },
  columns: "Columns", columnHint: "Check what each column measures. Unused columns are ignored.",
  ignore: "Ignore", time: "Time", outdoor: "Outdoor temperature",

  // 02 building and schedule
  step2: "Building",
  buildingType: "Building type", office: "Office", hotel: "Hotel", school: "School",
  roomType: "Room type", smallOffice: "Small office", openOffice: "Open-plan office",
  cooling: "Mechanical cooling", coolingHint: "Without cooling, summer temperatures are rated with the adaptive model. This needs an outdoor temperature column.",
  more: "Room data (optional)", volume: "Room volume", rt: "Reverberation time", df: "Daylight factor", radon: "Radon",
  hours: "Assessed hours",
  schedule: "Schedule", advanced: "Edit the schedule",
  addPeriod: "Add a period", removePeriod: "Remove period", copyMonday: "Copy Monday to Tue–Fri", closed: "Closed",
  publicHolidays: "Leave out public holidays",
  holidays: "Holidays", holidayName: "Name", first: "First day", last: "Last day", addHoliday: "Add a holiday",
  schoolHolidays: "Add typical Danish school holidays",
  schoolHolidaysHint: "Typical dates: each municipality sets its own, so check them against the school's calendar.",
  closedDays: "Single closed days", addClosedDay: "Add a day",
  perWeek: "h per week", resetSchedule: "Back to the profile hours",
  from: "From", to: "To",
  create: "Create labels", rating: "Rating…", ratingRoom: (i: number, n: number) => `Rating ${n} rooms…`,

  // 03 labels
  step3: "Labels",
  labelTitle: "TAIL label", overall: "Overall", building: "Building",
  buildingEyebrow: (n: number) => `Building · ${n} rooms`,
  download: "Download", svg: "SVG", png: "PNG", startOver: "Start over",
  allLabels: "All labels (ZIP)", zipping: "Packing…",
  parameters: "Parameters", parameter: "Parameter", value: "Value", ratingCol: "Rating", rule: "Rule",
  roomsRated: "Rooms", notRated: "Not rated", warnings: "Notes",
  basisTitle: "How the building is rated",

  // 04 report
  step4: "Report",
  reportLead: "The full hvx report of the building: EN 16798-1 categories per season, BR18 indicators, TAIL per room and for the building, and recommendations. It is built in this browser too.",
  makeReport: "Create the report", reportLoading: "Loading the report engine (about 13 MB, once)", reportMaking: "Building the report…",
  downloadHtml: "Download HTML", openTab: "Open in a new tab", printPdf: "Print or save as PDF",
  reportStale: "Settings changed since the report was made.", remake: "Update the report",

  // 05 dashboard
  step5: "Dashboard",
  dashboardLead: "Explore the rooms: sort the table, pick a room to see when and how often limits are exceeded.",
  kpiRooms: "Rooms analysed", kpiCategory: "EN 16798-1 category", kpiTarget: "Meet the target", kpiScore: "IEQ score", kpiTail: "TAIL building",
  categoryMix: "Rooms per EN 16798-1 category", tailMix: "Rooms per TAIL rating",
  search: "Find a room", co2Hours: "CO₂ > 1000 ppm", hotHours: "Above 26 °C", category: "Category", score: "Score",
  hoursUnitLong: "h", ofOccupied: "of occupied time",
  byHour: "CO₂ above 1000 ppm, by hour of day", byMonth: "CO₂ above 1000 ppm, by month", hotByMonth: "Hours above 26 °C, by month",
  measured: "Measured values (occupied hours)", mean: "Mean", min: "Min", max: "Max", compliance: "Within target",
  issues: "Findings", recommendations: "Recommendations", actions: "Building actions", noActions: "No actions needed.",
  priority: { high: "High", medium: "Medium", low: "Low" } as Record<string, string>,
  seasons: { winter: "Winter", summer: "Summer", all_year: "All year" } as Record<string, string>,
  adaptive: "adaptive",
  target: "target",
  selectRoom: "Pick a room in the table.",
  notInData: "Not measured",

  domains: { thermal: "Thermal", acoustic: "Acoustic", iaq: "Indoor air", luminous: "Light" },
  params: {
    temperature: "Temperature", relative_humidity: "Relative humidity", humidity: "Relative humidity", co2: "CO₂", noise: "Noise", illuminance: "Illuminance",
    pm25: "PM2.5", no2: "NO₂", formaldehyde: "Formaldehyde", benzene: "Benzene", radon: "Radon", ventilation: "Ventilation",
    mold: "Mould", daylight_factor: "Daylight factor", reverberation_time: "Reverberation time",
  } as Record<string, string>,
  short: {
    temperature: "Temperature", relative_humidity: "RH", co2: "CO₂", noise: "Noise", illuminance: "Lux", pm25: "PM2.5",
    no2: "NO₂", formaldehyde: "HCHO", benzene: "Benzene", radon: "Radon", ventilation: "Vent.", mold: "Mould",
    daylight_factor: "DF", reverberation_time: "RT",
  } as Record<string, string>,
  profiles: { office: "Office · TAIL (Wargocki et al. 2021)", hotel: "Hotel · TAIL (Wargocki et al. 2021)", school: "School · TAIL for schools (Tran 2024)" },
  basis: {
    office: "Each parameter of the building is the mean of the rooms' ratings (TAIL paper, Eq. 1); a domain takes its worst parameter.",
    hotel: "Each parameter of the building is the mean of the rooms' ratings (TAIL paper, Eq. 1); a domain takes its worst parameter.",
    school: "Each domain of the school is the mean of the classrooms' domain ratings (Tran 2024).",
  },
  period: "Measured", assessed: "assessed", days: "d", hoursUnit: "h",
  notMeasured: "not measured", madeWith: "Rated with hvx",
  method: "How the rating works",
  methodSteps: [
    ["Per room, per parameter", "Each parameter is rated I (best) to IV from the share of assessed hours in each band."],
    ["Domains and overall", "A domain takes its worst parameter, and the room its worst domain."],
    ["The building", "Offices and hotels: the mean of the rooms' parameter ratings (TAIL paper, Eq. 1). Schools: the mean of the classrooms' domain ratings (Tran 2024)."],
    ["The report", "EN 16798-1 categories for winter and summer (adaptive without cooling), BR18 indicators and recommendations, over the same hours."],
  ] as [string, string][],
  error: "Could not rate the files",
  reportError: "Could not build the report",
  footer: "© 2026 BAW · Bruno Adam · CVR 46539214 · København S",
  source: "Source code",
  dayNames: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
  dayNamesLong: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
};
type Dict = typeof en;

const da: Dict = {
  eyebrow: "Indeklima",
  heroEyebrow: "Indeklima · TAIL · EN 16798-1",
  title: "TAIL-mærker og en fuld rapport ud fra jeres målinger",
  lead: "Upload én CSV-fil pr. rum med et års målinger. Du får et TAIL-mærke for hvert rum og for bygningen, den fulde indeklimarapport og et interaktivt dashboard.",
  privacy: "Filerne bliver i din browser. Intet uploades.",
  nav: { labels: "Mærker", report: "Rapport", dashboard: "Dashboard", contact: "Kontakt" },
  langLabel: "Sprog",

  step1: "Rum",
  drop: "Træk CSV-filer hertil, én pr. rum",
  dropHint: "Et år (365 dage) med målinger pr. rum, én række pr. tidspunkt. Kolonner: tid og en eller flere af temperatur, CO₂, fugtighed, støj, lys, PM2.5, NO₂. Udetemperatur er valgfri.",
  choose: "Vælg filer", addRooms: "Tilføj rum", example: "Prøv en eksempelbygning", rows: "rækker",
  room: "Rum", file: "Fil", remove: "Fjern", details: "Kolonner og rumdata",
  roomsCount: (n: number) => (n === 1 ? "1 rum" : `${n} rum`),
  buildingName: "Bygningens navn", buildingPlaceholder: "f.eks. Nordskolen",
  engineLoading: "Indlæser beregningen", engineReady: "Beregningen er klar",
  engineSteps: { runtime: "Python", packages: "pandas og numpy", hvx: "hvx", report: "rapportmotoren" },
  columns: "Kolonner", columnHint: "Tjek, hvad hver kolonne måler. Kolonner uden valg springes over.",
  ignore: "Spring over", time: "Tid", outdoor: "Udetemperatur",

  step2: "Bygning",
  buildingType: "Bygningstype", office: "Kontor", hotel: "Hotel", school: "Skole",
  roomType: "Rumtype", smallOffice: "Enkeltkontor", openOffice: "Storrumskontor",
  cooling: "Mekanisk køling", coolingHint: "Uden køling vurderes sommertemperaturen med den adaptive model. Det kræver en kolonne med udetemperatur.",
  more: "Rumdata (valgfrit)", volume: "Rumvolumen", rt: "Efterklangstid", df: "Dagslysfaktor", radon: "Radon",
  hours: "Vurderet tid",
  schedule: "Skema", advanced: "Ret skemaet",
  addPeriod: "Tilføj periode", removePeriod: "Fjern periode", copyMonday: "Kopiér mandag til tir–fre", closed: "Lukket",
  publicHolidays: "Udelad helligdage",
  holidays: "Ferier", holidayName: "Navn", first: "Første dag", last: "Sidste dag", addHoliday: "Tilføj ferie",
  schoolHolidays: "Tilføj typiske skoleferier",
  schoolHolidaysHint: "Typiske datoer: hver kommune fastsætter sine egne, så tjek dem mod skolens kalender.",
  closedDays: "Enkelte lukkedage", addClosedDay: "Tilføj dag",
  perWeek: "t pr. uge", resetSchedule: "Tilbage til profilens tider",
  from: "Fra", to: "Til",
  create: "Lav mærkerne", rating: "Beregner…", ratingRoom: (i: number, n: number) => `Vurderer ${n} rum…`,

  step3: "Mærker",
  labelTitle: "TAIL-mærke", overall: "Samlet", building: "Bygning",
  buildingEyebrow: (n: number) => `Bygning · ${n} rum`,
  download: "Hent", svg: "SVG", png: "PNG", startOver: "Start forfra",
  allLabels: "Alle mærker (ZIP)", zipping: "Pakker…",
  parameters: "Parametre", parameter: "Parameter", value: "Værdi", ratingCol: "Vurdering", rule: "Regel",
  roomsRated: "Rum", notRated: "Ikke vurderet", warnings: "Bemærkninger",
  basisTitle: "Sådan vurderes bygningen",

  step4: "Rapport",
  reportLead: "Bygningens fulde hvx-rapport: EN 16798-1-kategorier pr. sæson, BR18-indikatorer, TAIL pr. rum og for bygningen samt anbefalinger. Den laves også i din browser.",
  makeReport: "Lav rapporten", reportLoading: "Indlæser rapportmotoren (ca. 13 MB, én gang)", reportMaking: "Laver rapporten…",
  downloadHtml: "Hent HTML", openTab: "Åbn i ny fane", printPdf: "Udskriv eller gem som PDF",
  reportStale: "Indstillingerne er ændret, siden rapporten blev lavet.", remake: "Opdatér rapporten",

  step5: "Dashboard",
  dashboardLead: "Udforsk rummene: sortér tabellen, og vælg et rum for at se, hvornår og hvor ofte grænserne overskrides.",
  kpiRooms: "Analyserede rum", kpiCategory: "EN 16798-1-kategori", kpiTarget: "Når målet", kpiScore: "IEQ-score", kpiTail: "TAIL bygning",
  categoryMix: "Rum pr. EN 16798-1-kategori", tailMix: "Rum pr. TAIL-vurdering",
  search: "Find et rum", co2Hours: "CO₂ > 1000 ppm", hotHours: "Over 26 °C", category: "Kategori", score: "Score",
  hoursUnitLong: "t", ofOccupied: "af brugstiden",
  byHour: "CO₂ over 1000 ppm, pr. time på dagen", byMonth: "CO₂ over 1000 ppm, pr. måned", hotByMonth: "Timer over 26 °C, pr. måned",
  measured: "Målte værdier (i brugstiden)", mean: "Middel", min: "Min", max: "Maks", compliance: "Inden for målet",
  issues: "Fund", recommendations: "Anbefalinger", actions: "Tiltag for bygningen", noActions: "Ingen tiltag nødvendige.",
  priority: { high: "Høj", medium: "Middel", low: "Lav" },
  seasons: { winter: "Vinter", summer: "Sommer", all_year: "Hele året" },
  adaptive: "adaptiv",
  target: "mål",
  selectRoom: "Vælg et rum i tabellen.",
  notInData: "Ikke målt",

  domains: { thermal: "Termisk", acoustic: "Akustik", iaq: "Luftkvalitet", luminous: "Lys" },
  params: {
    temperature: "Temperatur", relative_humidity: "Relativ fugtighed", humidity: "Relativ fugtighed", co2: "CO₂", noise: "Støj", illuminance: "Belysningsstyrke",
    pm25: "PM2.5", no2: "NO₂", formaldehyde: "Formaldehyd", benzene: "Benzen", radon: "Radon", ventilation: "Ventilation",
    mold: "Skimmel", daylight_factor: "Dagslysfaktor", reverberation_time: "Efterklangstid",
  },
  short: {
    temperature: "Temperatur", relative_humidity: "RF", co2: "CO₂", noise: "Støj", illuminance: "Lux", pm25: "PM2.5",
    no2: "NO₂", formaldehyde: "HCHO", benzene: "Benzen", radon: "Radon", ventilation: "Vent.", mold: "Skimmel",
    daylight_factor: "DF", reverberation_time: "RT",
  },
  profiles: { office: "Kontor · TAIL (Wargocki m.fl. 2021)", hotel: "Hotel · TAIL (Wargocki m.fl. 2021)", school: "Skole · TAIL for skoler (Tran 2024)" },
  basis: {
    office: "Bygningens parametre er middelværdien af rummenes vurderinger (TAIL-artiklen, lign. 1); et domæne får sin dårligste parameter.",
    hotel: "Bygningens parametre er middelværdien af rummenes vurderinger (TAIL-artiklen, lign. 1); et domæne får sin dårligste parameter.",
    school: "Skolens domæner er middelværdien af klasselokalernes domænevurderinger (Tran 2024).",
  },
  period: "Målt", assessed: "vurderet", days: "d", hoursUnit: "t",
  notMeasured: "ikke målt", madeWith: "Vurderet med hvx",
  method: "Sådan vurderes der",
  methodSteps: [
    ["Pr. rum, pr. parameter", "Hver parameter vurderes fra I (bedst) til IV ud fra andelen af den vurderede tid i hvert interval."],
    ["Domæner og samlet", "Et domæne får sin dårligste parameter, og rummet sit dårligste domæne."],
    ["Bygningen", "Kontorer og hoteller: middelværdien af rummenes parametervurderinger (TAIL-artiklen, lign. 1). Skoler: middelværdien af klasselokalernes domænevurderinger (Tran 2024)."],
    ["Rapporten", "EN 16798-1-kategorier for vinter og sommer (adaptiv uden køling), BR18-indikatorer og anbefalinger over de samme timer."],
  ],
  error: "Filerne kunne ikke vurderes",
  reportError: "Rapporten kunne ikke laves",
  footer: "© 2026 BAW · Bruno Adam · CVR 46539214 · København S",
  source: "Kildekode",
  dayNames: ["man", "tir", "ons", "tor", "fre", "lør", "søn"],
  dayNamesLong: ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"],
};

export const STRINGS: Record<Lang, Dict> = { en, da };

export function formatNumber(value: number, lang: Lang, digits = 0): string {
  // BAW: thin space between thousands; Danish decimal comma
  const fixed = value.toFixed(digits);
  const [int, dec] = fixed.split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return dec ? `${grouped}${lang === "da" ? "," : "."}${dec}` : grouped;
}

const time = (s: string | undefined, lang: Lang) => (lang === "da" ? (s ?? "").replace(":", ".") : s ?? "");

/** "Mon–Fri 08:00–17:00" / "man–fre 08.00–17.00"; per-day groups for advanced schedules. */
export function formatHours(
  o: { start?: string; end?: string; weekdays?: number[]; all_hours?: boolean; groups?: { days: number[]; hours: [string, string][] }[] },
  lang: Lang,
): string {
  if (o.all_hours) return lang === "da" ? "alle timer" : "all hours";
  const names = STRINGS[lang].dayNames;
  const span = (days: number[]) => {
    if (days.length === 7) return lang === "da" ? "alle dage" : "every day";
    const contiguous = days.length > 1 && days.every((d, i) => i === 0 || d === days[i - 1] + 1);
    return contiguous ? `${names[days[0]]}–${names[days[days.length - 1]]}` : days.map((d) => names[d]).join(", ");
  };
  const groups = o.groups?.length ? o.groups : [{ days: o.weekdays ?? [], hours: [[o.start ?? "", o.end ?? ""]] as [string, string][] }];
  return groups.map((g) => `${span(g.days)} ${g.hours.map(([a, b]) => `${time(a, lang)}–${time(b, lang)}`).join(", ")}`).join("; ");
}

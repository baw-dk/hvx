/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  AlertTriangle, Archive, BedDouble, Building2, ChevronDown, Download, ExternalLink, FilePlus2, FileText, FileUp, Loader2,
  Lock, Printer, RotateCcw, School, Trash2,
} from "lucide-react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DimensionRule, Logo } from "@/components/brand";
import { Chip, Dashboard } from "@/components/Dashboard";
import { ScheduleEditor, simpleSchedule, type EditableSchedule } from "@/components/ScheduleEditor";
import { TailSticker } from "@/components/TailSticker";
import { engine, type Label as TailLabel, type Progress, type RateOptions, type ReportData, type RoomInput } from "@/lib/engine";
import { exampleBuilding } from "@/lib/example";
import { pngBlob, save, slugify, svgBlob } from "@/lib/export";
import { formatNumber, STRINGS, type Lang } from "@/lib/i18n";
import { DOMAINS } from "@/lib/tail";
import { zip } from "@/lib/zip";

type BuildingType = RateOptions["building_type"];
const COLUMN_CHOICES = ["time", "temperature", "co2", "relative_humidity", "noise", "illuminance", "pm25", "no2",
  "formaldehyde", "benzene", "radon", "outdoor_temperature", "ignore"] as const;
const SITE = "https://brunoadam.eu";

interface RoomFile {
  id: number;
  file: string;
  text: string;
  rows: number;
  years: number[];
  columns: Record<string, string>;
  name: string;
  volume?: string;
  rt?: string;
  df?: string;
  radon?: string;
}

let nextRoomId = 1;
const roomNameFrom = (file: string) => file.replace(/\.[^.]+$/, "").replace(/[_]+/g, " ").replace(/\s+/g, " ").trim();
const num = (v?: string) => (v && !Number.isNaN(Number(v.replace(",", "."))) ? Number(v.replace(",", ".")) : undefined);
const yearsIn = (text: string) => {
  const lines = text.trim().split(/\r?\n/);
  const found = [lines[1], lines[lines.length - 1]].map((l) => /\b((?:19|20)\d{2})[-/.]\d/.exec(l ?? "")?.[1]).filter(Boolean).map(Number);
  return found.length ? Array.from({ length: Math.max(...found) - Math.min(...found) + 1 }, (_, i) => Math.min(...found) + i) : [];
};

function SectionHead({ n, eyebrow, title, lead, id }: { n: string; eyebrow: string; title?: string; lead?: string; id?: string }) {
  return (
    <div className="flex max-w-[40rem] flex-col gap-3">
      <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground"><span className="font-mono text-signal-ink">{n}</span> · {eyebrow}</div>
      {title && <h2 id={id} className="m-0 font-display text-[clamp(1.75rem,3vw,2.25rem)] font-bold leading-[1.15] tracking-[-0.02em]">{title}</h2>}
      {lead && <p className="m-0 text-[18px] leading-7 text-muted-foreground">{lead}</p>}
    </div>
  );
}

function StepCard({ n, title, active, done, children, footer, className }: {
  n: string; title: string; active?: boolean; done?: boolean; children: React.ReactNode; footer?: React.ReactNode; className?: string;
}) {
  return (
    <Card className={`${active ? "border-t-[3px] border-t-signal" : ""} ${className ?? ""}`}>
      <CardHeader className="gap-1">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          <span className="font-mono">{n}</span>
          {done && <span className="size-1.5 rounded-full bg-success" aria-hidden />}
        </div>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
      {footer && <CardFooter>{footer}</CardFooter>}
    </Card>
  );
}

export default function App() {
  const [lang, setLang] = React.useState<Lang>(() => (navigator.language?.startsWith("da") ? "da" : "en"));
  const t = STRINGS[lang];
  React.useEffect(() => { document.documentElement.lang = lang; }, [lang]);

  // engine
  const [engineState, setEngineState] = React.useState<"loading" | "ready" | "error">("loading");
  const [progress, setProgress] = React.useState<Progress>("runtime");
  React.useEffect(() => {
    const off = engine.onProgress(setProgress);
    engine.init().then(() => setEngineState("ready")).catch(() => setEngineState("error"));
    return () => { off(); };
  }, []);

  // inputs
  const [rooms, setRooms] = React.useState<RoomFile[]>([]);
  const [buildingName, setBuildingName] = React.useState("");
  const [buildingType, setBuildingType] = React.useState<BuildingType>("school");
  const [roomType, setRoomType] = React.useState("small_office");
  const [cooling, setCooling] = React.useState(false);
  const [profileSchedule, setProfileSchedule] = React.useState<EditableSchedule>(() => simpleSchedule("08:00", "17:00", [0, 1, 2, 3, 4], true));
  const [schedule, setSchedule] = React.useState<EditableSchedule>(profileSchedule);
  const [dragging, setDragging] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const years = React.useMemo(() => [...new Set(rooms.flatMap((r) => r.years))].sort(), [rooms]);

  // results
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [labels, setLabels] = React.useState<{ rooms: TailLabel[]; building: TailLabel | null; key: string } | null>(null);
  const [selected, setSelected] = React.useState<number>(-1); // -1: building
  const [zipping, setZipping] = React.useState(false);
  const [report, setReport] = React.useState<{ html: string; data: ReportData; key: string; lang: Lang } | null>(null);
  const [reportBusy, setReportBusy] = React.useState(false);
  const [reportError, setReportError] = React.useState<string | null>(null);

  // profile hours and cooling per building type (TAIL profiles)
  React.useEffect(() => {
    setCooling(buildingType !== "school");
    if (engineState !== "ready") return;
    engine.hours(buildingType).then((h) => {
      const s = simpleSchedule(h.start, h.end, h.weekdays, buildingType !== "hotel");
      setProfileSchedule(s);
      setSchedule(s);
    }).catch(() => {});
  }, [buildingType, engineState]);

  const addFiles = async (files: { name: string; text: string; file: string }[]) => {
    setError(null);
    const added: RoomFile[] = [];
    for (const f of files) {
      try {
        const detected = await engine.detect(f.text);
        added.push({
          id: nextRoomId++, file: f.file, text: f.text, name: f.name,
          rows: Math.max(0, f.text.split(/\r?\n/).filter(Boolean).length - 1), years: yearsIn(f.text),
          columns: Object.fromEntries(Object.entries(detected).map(([k, v]) => [k, v ?? "ignore"])),
        });
      } catch (e) {
        setError(`${f.file}: ${(e as Error).message}`);
      }
    }
    setRooms((r) => [...r, ...added]);
  };
  const readFiles = async (list: FileList | File[]) =>
    addFiles(await Promise.all([...list].map(async (f) => ({ name: roomNameFrom(f.name), file: f.name, text: await f.text() }))));
  const useExample = () => {
    setBuildingType("school");
    setBuildingName(lang === "da" ? "Eksempelskolen" : "Example School");
    addFiles(exampleBuilding(lang).map((r) => ({ name: r.name, file: r.file, text: r.csv })));
  };
  const updateRoom = (id: number, patch: Partial<RoomFile>) => setRooms((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const reset = () => { setRooms([]); setLabels(null); setReport(null); setError(null); setReportError(null); setBuildingName(""); };

  const roomInputs = (): RoomInput[] => rooms.map((r) => {
    const spot: Record<string, number> = {};
    if (num(r.rt) !== undefined && buildingType === "school") spot.reverberation_time = num(r.rt)!;
    if (num(r.df) !== undefined) spot.daylight_factor = num(r.df)!;
    if (num(r.radon) !== undefined) spot.radon = num(r.radon)!;
    return { name: r.name || roomNameFrom(r.file), csv: r.text, columns: r.columns, volume_m3: num(r.volume) ?? null, spot_values: spot };
  });
  const cleanSchedule = { periods: schedule.periods, holiday_periods: schedule.holiday_periods, closed_days: schedule.closed_days, public_holidays: schedule.public_holidays };
  const inputsKey = JSON.stringify([rooms.map((r) => [r.id, r.name, r.columns, r.volume, r.rt, r.df, r.radon]), buildingName, buildingType, roomType, cooling, cleanSchedule]);
  const shownName = buildingName || (lang === "da" ? "Bygning" : "Building");

  const create = async () => {
    if (!rooms.length) return;
    setBusy(true);
    setError(null);
    try {
      const result = await engine.labels(roomInputs(), shownName, {
        building_type: buildingType, room_type: buildingType === "office" ? roomType : null,
        mechanical_cooling: cooling ? null : false, schedule: cleanSchedule,
      });
      setLabels({ ...result, key: inputsKey });
      setSelected(result.building ? -1 : 0);
      requestAnimationFrame(() => document.getElementById("labels-result")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const makeReport = async () => {
    if (!rooms.length) return;
    setReportBusy(true);
    setReportError(null);
    try {
      const result = await engine.report(roomInputs(), {
        building_name: shownName, building_type: buildingType, room_type: buildingType === "office" ? roomType : null,
        mechanical_cooling: cooling ? null : false, language: lang, schedule: cleanSchedule,
      });
      setReport({ ...result, key: inputsKey, lang });
    } catch (e) {
      setReportError((e as Error).message);
    } finally {
      setReportBusy(false);
    }
  };

  // labels: the building first (with more than one room), then the rooms
  const allLabels: { label: TailLabel; file: string }[] = labels
    ? [...(labels.building ? [{ label: labels.building, file: `${slugify(shownName)}-building` }] : []),
      ...labels.rooms.map((l) => ({ label: l, file: `${slugify(shownName)}-${slugify(l.name ?? "room")}` }))]
    : [];
  const current = labels ? (selected === -1 ? labels.building : labels.rooms[selected]) ?? labels.rooms[0] : null;
  const currentFile = labels ? allLabels[(labels.building ? 1 : 0) + selected]?.file ?? "tail-label" : "tail-label";
  const markup = (label: TailLabel) => renderToStaticMarkup(<TailSticker label={label} lang={lang} />);
  const downloadOne = async (label: TailLabel, file: string, kind: "png" | "svg") =>
    save(kind === "png" ? await pngBlob(markup(label)) : svgBlob(markup(label)), `${file}.${kind}`);
  const downloadAll = async () => {
    setZipping(true);
    try {
      const files: { name: string; data: Blob }[] = [];
      for (const { label, file } of allLabels) {
        const m = markup(label);
        files.push({ name: `${file}.png`, data: await pngBlob(m) }, { name: `${file}.svg`, data: svgBlob(m) });
      }
      save(await zip(files), `${slugify(shownName)}-tail-labels.zip`);
    } finally {
      setZipping(false);
    }
  };
  const labelsStale = labels && labels.key !== inputsKey;
  const reportStale = report && (report.key !== inputsKey || report.lang !== lang);
  const columnName = (c: string) => (c === "time" ? t.time : c === "ignore" ? t.ignore : c === "outdoor_temperature" ? t.outdoor : t.params[c] ?? c);
  const ready = engineState === "ready";

  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:bg-card focus:px-3 focus:py-2">Skip</a>
      <header className="sticky top-0 z-20 border-b border-line bg-[color-mix(in_srgb,var(--paper)_92%,transparent)] backdrop-blur-md backdrop-saturate-150">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-x-4 gap-y-3 px-4 py-3.5 sm:px-6">
          <a href={SITE} aria-label="BAW" className="text-foreground no-underline"><Logo size={28} /></a>
          <nav aria-label="Main" className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[15px] font-medium">
            <a href="#labels" className="text-muted-foreground no-underline hover:text-foreground max-sm:hidden">{t.nav.labels}</a>
            <a href="#report" className="text-muted-foreground no-underline hover:text-foreground max-sm:hidden">{t.nav.report}</a>
            <a href="#dashboard" className="text-muted-foreground no-underline hover:text-foreground max-sm:hidden">{t.nav.dashboard}</a>
            <div className="inline-flex items-center gap-0.5 font-mono text-[12px] font-medium tracking-[0.04em]" role="group" aria-label={t.langLabel}>
              {(["en", "da"] as const).map((l) => (
                <button key={l} type="button" onClick={() => setLang(l)} aria-pressed={lang === l} lang={l}
                  className={`rounded-sm px-1.5 py-1 hover:bg-sunken ${lang === l ? "text-foreground shadow-[inset_0_-2px_0_var(--signal)]" : "text-muted-foreground hover:text-foreground"}`}>
                  {l.toUpperCase()}
                </button>
              ))}
            </div>
            <Button asChild size="sm"><a href={`${SITE}/#contact`}>{t.nav.contact}</a></Button>
          </nav>
        </div>
      </header>

      <main id="main">
        {/* hero */}
        <section className="mx-auto flex max-w-[1200px] flex-col gap-6 px-4 pb-14 pt-14 sm:px-6 sm:pb-[88px] sm:pt-24">
          <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{t.heroEyebrow}</div>
          <h1 className="m-0 max-w-[16ch] font-display text-[clamp(2.5rem,5vw,4.25rem)] font-bold leading-[1.02] tracking-[-0.03em]">{t.title}</h1>
          <div className="w-[200px] text-foreground"><DimensionRule /></div>
          <p className="m-0 max-w-[36rem] text-[18px] leading-7 text-muted-foreground">{t.lead}</p>
          <p className="m-0 inline-flex items-center gap-2 text-[14px]"><Lock className="size-4" aria-hidden /> {t.privacy}</p>
        </section>

        {/* 01–03: rooms, building, labels */}
        <section id="labels" className="border-t border-line" aria-labelledby="labels-title">
          <div className="mx-auto flex max-w-[1200px] flex-col gap-10 px-4 py-16 sm:px-6 sm:py-[88px]">
            <h2 id="labels-title" className="sr-only">{t.nav.labels}</h2>
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
              <div className="flex min-w-0 flex-col gap-6">
                {/* 01 rooms */}
                <StepCard n="01" title={t.step1} active={!rooms.length} done={rooms.length > 0}
                  footer={
                    <span className="inline-flex items-center gap-2 text-[13px] text-muted-foreground">
                      {engineState === "loading" && <><Loader2 className="size-4 animate-spin" aria-hidden /> {t.engineLoading}: {t.engineSteps[progress]}…</>}
                      {engineState === "ready" && <><span className="size-2 rounded-full bg-success" aria-hidden /> {t.engineReady}</>}
                      {engineState === "error" && <><AlertTriangle className="size-4 text-danger" aria-hidden /> {t.error}</>}
                    </span>
                  }>
                  <input ref={inputRef} type="file" multiple accept=".csv,text/csv,text/plain" className="sr-only" tabIndex={-1}
                    onChange={(e) => { if (e.target.files?.length) readFiles(e.target.files); e.target.value = ""; }} />
                  <div
                    onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={(e) => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files.length) readFiles(e.dataTransfer.files); }}
                    className={rooms.length ? "flex flex-col gap-4" : `flex flex-col items-center gap-3 rounded-md border-2 border-dashed px-6 py-10 text-center transition-colors ${dragging ? "border-primary bg-sunken" : "border-input"}`}
                  >
                    {!rooms.length ? (
                      <>
                        <FileUp className="size-8 text-muted-foreground" aria-hidden />
                        <div className="font-display text-xl font-medium">{t.drop}</div>
                        <p className="m-0 max-w-[520px] text-[13px] leading-5 text-muted-foreground">{t.dropHint}</p>
                        <div className="mt-2 flex flex-wrap justify-center gap-2">
                          <Button onClick={() => inputRef.current?.click()} disabled={!ready}><FileUp aria-hidden /> {t.choose}</Button>
                          <Button variant="quiet" onClick={useExample} disabled={!ready}>{t.example}</Button>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="flex flex-col gap-2">
                          <Label htmlFor="building-name">{t.buildingName}</Label>
                          <Input id="building-name" value={buildingName} placeholder={t.buildingPlaceholder} maxLength={44} onChange={(e) => setBuildingName(e.target.value)} />
                        </div>
                        <div className={`rounded-md border ${dragging ? "border-primary bg-sunken" : "border-transparent"}`}>
                          <div className="flex items-center justify-between border-b-2 border-foreground pb-2 text-[13px] font-semibold text-muted-foreground">
                            <span>{t.roomsCount(rooms.length)}</span>
                            <span className="font-mono font-normal tabular">{formatNumber(rooms.reduce((n, r) => n + r.rows, 0), lang)} {t.rows}</span>
                          </div>
                          <ul className="m-0 list-none p-0">
                            {rooms.map((r) => (
                              <li key={r.id} className="border-b border-line py-3">
                                <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                                  <Input aria-label={`${t.room}: ${r.file}`} value={r.name} maxLength={44} onChange={(e) => updateRoom(r.id, { name: e.target.value })}
                                    className="h-9 min-w-0 flex-1 basis-48 font-semibold" />
                                  <span className="min-w-0 max-w-[14rem] truncate font-mono text-[12px] text-muted-foreground" title={r.file}>{r.file}</span>
                                  <span className="font-mono text-[12px] text-muted-foreground tabular">{formatNumber(r.rows, lang)}</span>
                                  <button type="button" aria-label={`${t.remove}: ${r.name}`} onClick={() => setRooms((rs) => rs.filter((x) => x.id !== r.id))}
                                    className="inline-flex size-8 items-center justify-center rounded-sm text-muted-foreground hover:bg-sunken hover:text-foreground">
                                    <Trash2 className="size-4" aria-hidden />
                                  </button>
                                </div>
                                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                                  {Object.entries(r.columns).filter(([, v]) => v !== "ignore").map(([k, v]) => (
                                    <Badge key={k} tone={v === "time" ? "neutral" : "info"}>{columnName(v)}</Badge>
                                  ))}
                                </div>
                                <Collapsible>
                                  <CollapsibleTrigger className="group mt-2 inline-flex items-center gap-1 text-[13px] font-semibold text-blueprint">
                                    {t.details} <ChevronDown className="size-4 transition-transform group-data-[state=open]:rotate-180" aria-hidden />
                                  </CollapsibleTrigger>
                                  <CollapsibleContent className="mt-3 flex flex-col gap-4">
                                    <p className="m-0 text-[13px] text-muted-foreground">{t.columnHint}</p>
                                    <div className="grid gap-3 sm:grid-cols-2">
                                      {Object.entries(r.columns).map(([col, value]) => (
                                        <div key={col} className="flex flex-col gap-1.5">
                                          <Label className="truncate font-mono text-[12px] font-medium">{col}</Label>
                                          <Select value={value} onValueChange={(v) => updateRoom(r.id, { columns: { ...r.columns, [col]: v } })}>
                                            <SelectTrigger><SelectValue /></SelectTrigger>
                                            <SelectContent>{COLUMN_CHOICES.map((c) => <SelectItem key={c} value={c}>{columnName(c)}</SelectItem>)}</SelectContent>
                                          </Select>
                                        </div>
                                      ))}
                                    </div>
                                    <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{t.more}</div>
                                    <div className="grid gap-3 sm:grid-cols-2">
                                      <div className="flex flex-col gap-1.5"><Label htmlFor={`vol-${r.id}`}>{t.volume} (m³)</Label>
                                        <Input id={`vol-${r.id}`} inputMode="decimal" value={r.volume ?? ""} onChange={(e) => updateRoom(r.id, { volume: e.target.value })} /></div>
                                      {buildingType === "school" && (
                                        <div className="flex flex-col gap-1.5"><Label htmlFor={`rt-${r.id}`}>{t.rt} (s)</Label>
                                          <Input id={`rt-${r.id}`} inputMode="decimal" value={r.rt ?? ""} onChange={(e) => updateRoom(r.id, { rt: e.target.value })} /></div>
                                      )}
                                      <div className="flex flex-col gap-1.5"><Label htmlFor={`df-${r.id}`}>{t.df} (%)</Label>
                                        <Input id={`df-${r.id}`} inputMode="decimal" value={r.df ?? ""} onChange={(e) => updateRoom(r.id, { df: e.target.value })} /></div>
                                      <div className="flex flex-col gap-1.5"><Label htmlFor={`radon-${r.id}`}>{t.radon} (Bq/m³)</Label>
                                        <Input id={`radon-${r.id}`} inputMode="decimal" value={r.radon ?? ""} onChange={(e) => updateRoom(r.id, { radon: e.target.value })} /></div>
                                    </div>
                                  </CollapsibleContent>
                                </Collapsible>
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Button variant="quiet" onClick={() => inputRef.current?.click()}><FilePlus2 aria-hidden /> {t.addRooms}</Button>
                          <Button variant="ghost" onClick={reset}><RotateCcw aria-hidden /> {t.startOver}</Button>
                        </div>
                      </>
                    )}
                  </div>
                </StepCard>

                {/* 02 building and schedule */}
                <StepCard n="02" title={t.step2} active={rooms.length > 0 && !labels} done={!!labels} className={!rooms.length ? "opacity-60" : undefined}
                  footer={
                    <Button variant="signal" size="lg" className="w-full sm:w-auto" disabled={!rooms.length || busy || !ready} onClick={create}>
                      {busy ? <><Loader2 className="animate-spin" aria-hidden /> {t.ratingRoom(0, rooms.length)}</> : t.create}
                    </Button>
                  }>
                  <div className="flex flex-col gap-6">
                    <div className="flex flex-col gap-2">
                      <Label>{t.buildingType}</Label>
                      <Tabs value={buildingType} onValueChange={(v) => setBuildingType(v as BuildingType)}>
                        <TabsList>
                          <TabsTrigger value="office" disabled={!rooms.length}><Building2 aria-hidden /> {t.office}</TabsTrigger>
                          <TabsTrigger value="hotel" disabled={!rooms.length}><BedDouble aria-hidden /> {t.hotel}</TabsTrigger>
                          <TabsTrigger value="school" disabled={!rooms.length}><School aria-hidden /> {t.school}</TabsTrigger>
                        </TabsList>
                      </Tabs>
                      <p className="m-0 text-[13px] text-muted-foreground">{t.profiles[buildingType]}</p>
                    </div>
                    {buildingType === "office" && (
                      <div className="flex max-w-xs flex-col gap-2">
                        <Label>{t.roomType}</Label>
                        <Select value={roomType} onValueChange={setRoomType} disabled={!rooms.length}>
                          <SelectTrigger><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="small_office">{t.smallOffice}</SelectItem>
                            <SelectItem value="open_office">{t.openOffice}</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    )}
                    <ScheduleEditor value={schedule} onChange={setSchedule} profile={profileSchedule} lang={lang} years={years}
                      loadHolidays={engine.holidays} disabled={!rooms.length} />
                    <div className="flex items-start justify-between gap-4 rounded-md border border-line p-4">
                      <div>
                        <Label htmlFor="cooling">{t.cooling}</Label>
                        <p className="m-0 mt-1 text-[13px] leading-5 text-muted-foreground">{t.coolingHint}</p>
                        {!cooling && rooms.length > 0 && !rooms.some((r) => Object.values(r.columns).includes("outdoor_temperature")) && (
                          <p className="m-0 mt-2 inline-flex items-center gap-1.5 text-[13px] text-signal-ink"><AlertTriangle className="size-4" aria-hidden /> {t.outdoor}?</p>
                        )}
                      </div>
                      <Switch id="cooling" checked={cooling} onCheckedChange={setCooling} disabled={!rooms.length} />
                    </div>
                  </div>
                </StepCard>

                {error && <Alert tone="danger"><AlertTriangle aria-hidden /><div><strong>{t.error}.</strong> {error}</div></Alert>}

                {/* 03 the labels, as a list */}
                {labels && (
                  <div id="labels-result" className="scroll-mt-24">
                    <StepCard n="03" title={t.step3} done
                      footer={
                        <div className="flex w-full flex-wrap items-center justify-between gap-2">
                          {labelsStale ? (
                            <span className="inline-flex items-center gap-2 text-[13px] text-signal-ink"><AlertTriangle className="size-4" aria-hidden /> {t.reportStale}</span>
                          ) : <span />}
                          <div className="flex flex-wrap gap-2">
                            {labelsStale && <Button variant="quiet" onClick={create} disabled={busy}><RotateCcw aria-hidden /> {t.create}</Button>}
                            <Button onClick={downloadAll} disabled={zipping}>
                              {zipping ? <Loader2 className="animate-spin" aria-hidden /> : <Archive aria-hidden />} {zipping ? t.zipping : t.allLabels}
                            </Button>
                          </div>
                        </div>
                      }>
                      <div className="overflow-x-auto">
                        <table className="w-full text-[14px]">
                          <thead>
                            <tr className="border-b-2 border-foreground text-left text-[13px] text-muted-foreground">
                              <th className="py-2 pr-3 font-semibold">{t.roomsRated}</th>
                              <th className="py-2 pr-3 font-semibold">TAIL</th>
                              <th className="py-2 pr-3 font-semibold max-sm:hidden">T · A · I · L</th>
                              <th className="py-2 text-right font-semibold"><span className="sr-only">{t.download}</span></th>
                            </tr>
                          </thead>
                          <tbody>
                            {allLabels.map(({ label, file }, i) => {
                              const index = labels.building ? i - 1 : i;
                              const active = index === selected;
                              return (
                                <tr key={file + i} aria-selected={active}
                                  className={`border-b border-line transition-colors hover:bg-blueprint-soft ${active ? "bg-blueprint-soft" : ""} ${label.kind === "building" ? "border-b-foreground" : ""}`}>
                                  <td className="py-2 pr-3">
                                    <button type="button" onClick={() => setSelected(index)} className={`text-left hover:text-blueprint ${label.kind === "building" ? "font-display text-[16px] font-bold" : "font-semibold"}`}>
                                      {label.kind === "building" ? `${label.name} · ${t.building}` : label.name}
                                    </button>
                                  </td>
                                  <td className="py-2 pr-3"><Chip rating={label.overall} /></td>
                                  <td className="py-2 pr-3 max-sm:hidden">
                                    <span className="inline-flex gap-1">{DOMAINS.map((d) => <Chip key={d} rating={label.domains[d]} size="sm" title={`${t.domains[d]}: ${label.domains[d] ?? t.notMeasured}`} />)}</span>
                                  </td>
                                  <td className="py-2 text-right whitespace-nowrap">
                                    <Button size="sm" variant="ghost" onClick={() => downloadOne(label, file, "png")} aria-label={`${t.download} ${t.png}: ${label.name}`}><Download aria-hidden /> {t.png}</Button>
                                    <Button size="sm" variant="ghost" onClick={() => downloadOne(label, file, "svg")} aria-label={`${t.download} ${t.svg}: ${label.name}`}>{t.svg}</Button>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      {labels.building && (
                        <p className="m-0 mt-4 text-[13px] leading-5 text-muted-foreground"><strong className="text-foreground">{t.basisTitle}.</strong> {t.basis[labels.building.profile]}</p>
                      )}
                      {current && (current.warnings.length > 0 || Object.keys(current.not_rated).length > 0) && (
                        <div className="mt-4 flex flex-col gap-1.5">
                          <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{t.warnings} · {current.name}</div>
                          {current.warnings.map((w) => <p key={w} className="m-0 text-[13px] text-muted-foreground">{w}</p>)}
                          {Object.entries(current.not_rated).map(([k, why]) => <p key={k} className="m-0 text-[13px] text-muted-foreground">{t.params[k] ?? k}: {why}</p>)}
                        </div>
                      )}
                    </StepCard>
                  </div>
                )}
              </div>

              {/* the chosen label */}
              <aside className={`lg:sticky lg:top-24 lg:self-start ${current ? "" : "hidden lg:block"}`} aria-label={t.step3}>
                <Card>
                  <CardContent className="flex flex-col items-center gap-4">
                    {current ? (
                      <>
                        <TailSticker label={current} lang={lang} embedFonts={false} />
                        <div className="flex w-full flex-wrap justify-center gap-2">
                          <Button onClick={() => downloadOne(current, currentFile, "png")}><Download aria-hidden /> {t.download} {t.png}</Button>
                          <Button variant="quiet" onClick={() => downloadOne(current, currentFile, "svg")}><Download aria-hidden /> {t.svg}</Button>
                        </div>
                      </>
                    ) : (
                      <div className="flex aspect-[420/600] w-full max-w-[420px] items-center justify-center rounded-md border border-dashed border-input bg-sunken">
                        <span className="font-display text-[64px] font-bold text-line">TAIL</span>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </aside>
            </div>
          </div>
        </section>

        {/* 04 report */}
        <section id="report" className="border-t border-line bg-card" aria-labelledby="report-title">
          <div className="mx-auto flex max-w-[1200px] flex-col gap-8 px-4 py-16 sm:px-6 sm:py-[88px]">
            <SectionHead n="04" eyebrow={t.step4} title={t.step4} lead={t.reportLead} id="report-title" />
            <div className="flex flex-wrap items-center gap-3">
              <Button size="lg" variant={report ? "quiet" : "default"} disabled={!rooms.length || reportBusy || !ready} onClick={makeReport}>
                {reportBusy ? <Loader2 className="animate-spin" aria-hidden /> : <FileText aria-hidden />}
                {reportBusy ? (progress === "report" ? t.reportLoading : t.reportMaking) : report ? t.remake : t.makeReport}
              </Button>
              {report && (
                <>
                  <Button variant="quiet" onClick={() => save(new Blob([report.html], { type: "text/html" }), `${slugify(shownName)}-report.html`)}><Download aria-hidden /> {t.downloadHtml}</Button>
                  <Button variant="ghost" onClick={() => window.open(URL.createObjectURL(new Blob([report.html], { type: "text/html" })), "_blank", "noopener")}><ExternalLink aria-hidden /> {t.openTab}</Button>
                  <Button variant="ghost" onClick={() => window.open(URL.createObjectURL(new Blob(
                    [report.html.replace("</body>", "<script>addEventListener('load',()=>print())</script></body>")], { type: "text/html" })), "_blank")}>
                    <Printer aria-hidden /> {t.printPdf}
                  </Button>
                </>
              )}
            </div>
            {reportStale && <p className="m-0 inline-flex items-center gap-2 text-[14px] text-signal-ink"><AlertTriangle className="size-4" aria-hidden /> {t.reportStale}</p>}
            {reportError && <Alert tone="danger"><AlertTriangle aria-hidden /><div><strong>{t.reportError}.</strong> {reportError}</div></Alert>}
            {report && (
              // Scripts (table sorting) run, but in an opaque origin: the report cannot reach the app.
              <iframe title={`${t.step4}: ${shownName}`} srcDoc={report.html} sandbox="allow-scripts allow-popups"
                className="h-[80vh] min-h-[520px] w-full rounded-md border border-line bg-white" />
            )}
          </div>
        </section>

        {/* 05 dashboard */}
        <section id="dashboard" className="border-t border-line" aria-labelledby="dashboard-title">
          <div className="mx-auto flex max-w-[1200px] flex-col gap-8 px-4 py-16 sm:px-6 sm:py-[88px]">
            <SectionHead n="05" eyebrow={t.step5} title={t.step5} lead={t.dashboardLead} id="dashboard-title" />
            {report ? (
              <Dashboard data={report.data} building={labels?.building ?? null} lang={lang} />
            ) : (
              <div className="flex flex-col items-start gap-3 rounded-md border border-dashed border-input p-8">
                <p className="m-0 text-muted-foreground">{t.reportLead}</p>
                <Button disabled={!rooms.length || reportBusy || !ready} onClick={makeReport}>
                  {reportBusy ? <Loader2 className="animate-spin" aria-hidden /> : <FileText aria-hidden />} {t.makeReport}
                </Button>
              </div>
            )}
          </div>
        </section>

        {/* method */}
        <section className="border-t border-line bg-card" aria-labelledby="method-title">
          <div className="mx-auto flex max-w-[1200px] flex-col gap-10 px-4 py-16 sm:px-6 sm:py-[88px]">
            <h2 id="method-title" className="m-0 font-display text-[clamp(1.75rem,3vw,2.25rem)] font-bold leading-[1.15] tracking-[-0.02em]">{t.method}</h2>
            <ol className="m-0 grid list-none gap-x-10 gap-y-8 p-0 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]">
              {t.methodSteps.map(([title, text], i) => (
                <li key={title} className="flex flex-col gap-2.5">
                  <div className="font-mono text-[13px] font-medium text-signal-ink">{String(i + 1).padStart(2, "0")}</div>
                  <h3 className="m-0 font-display text-[20px] font-medium leading-7 tracking-[-0.01em]">{title}</h3>
                  <p className="m-0 text-muted-foreground">{text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-4 px-4 py-8 text-[13px] leading-5 text-muted-foreground sm:px-6">
          <span className="text-foreground"><Logo size={22} rule={false} mono /></span>
          <span>{t.footer}</span>
          <span className="flex flex-wrap gap-x-5 gap-y-2">
            <a className="text-muted-foreground hover:text-foreground" href="https://github.com/baw-dk/hvx">{t.source} · hvx (MPL-2.0)</a>
            <a className="text-muted-foreground hover:text-foreground" href={SITE}>brunoadam.eu</a>
          </span>
        </div>
      </footer>
    </div>
  );
}

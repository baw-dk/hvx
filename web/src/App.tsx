/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/. */
import * as React from "react";
import { AlertTriangle, BedDouble, Building2, ChevronDown, Download, FileUp, Loader2, Lock, RotateCcw, School } from "lucide-react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardEyebrow, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TailSticker } from "@/components/TailSticker";
import { engine, type Label as TailLabel, type Progress, type RateOptions } from "@/lib/engine";
import { downloadPng, downloadSvg, slugify } from "@/lib/export";
import { exampleCsv } from "@/lib/example";
import { formatNumber, STRINGS, type Lang } from "@/lib/i18n";
import { color, ink } from "@/lib/tail";

type BuildingType = RateOptions["building_type"];
const COLUMN_CHOICES = ["time", "temperature", "co2", "relative_humidity", "noise", "illuminance", "pm25", "no2",
  "formaldehyde", "benzene", "radon", "outdoor_temperature", "ignore"] as const;

function Logo() {
  // Live BAW logo: "baw" in Space Grotesk on a dimension rule with signal ticks
  return (
    <div className="inline-flex flex-col items-stretch" role="img" aria-label="baw">
      <span className="font-display text-[34px] font-bold leading-[0.95] tracking-[-0.03em]" aria-hidden>baw</span>
      <svg className="mt-1.5 h-4 w-full overflow-visible" viewBox="0 0 76 16" aria-hidden>
        <line x1="3" y1="8" x2="73" y2="8" stroke="currentColor" strokeWidth="2" />
        <line x1="3" y1="1" x2="3" y2="15" stroke="currentColor" strokeWidth="2" />
        <line x1="73" y1="1" x2="73" y2="15" stroke="currentColor" strokeWidth="2" />
        <line x1="0" y1="11.5" x2="6" y2="4.5" stroke="var(--signal)" strokeWidth="3" strokeLinecap="round" />
        <line x1="70" y1="11.5" x2="76" y2="4.5" stroke="var(--signal)" strokeWidth="3" strokeLinecap="round" />
      </svg>
    </div>
  );
}

function Step({ n, active, done }: { n: number; active?: boolean; done?: boolean }) {
  return (
    <span className={`inline-flex size-7 items-center justify-center rounded-sm font-mono text-[13px] font-medium ${
      active ? "bg-primary text-primary-foreground" : done ? "bg-signal text-on-signal" : "bg-sunken text-muted-foreground"}`}>
      {n}
    </span>
  );
}

function RatingChip({ rating }: { rating?: string | null }) {
  return (
    <span className="inline-flex min-w-9 justify-center rounded-sm px-2 font-display text-[13px] font-bold leading-6"
      style={{ background: color(rating as never), color: ink(rating as never) }}>
      {rating ?? "–"}
    </span>
  );
}

export default function App() {
  const [lang, setLang] = React.useState<Lang>(() => (navigator.language?.startsWith("da") ? "da" : "en"));
  const t = STRINGS[lang];
  React.useEffect(() => { document.documentElement.lang = lang; }, [lang]);

  const [engineState, setEngineState] = React.useState<"loading" | "ready" | "error">("loading");
  const [progress, setProgress] = React.useState<Progress>("runtime");
  React.useEffect(() => {
    const off = engine.onProgress(setProgress);
    engine.init().then(() => setEngineState("ready")).catch(() => setEngineState("error"));
    return () => { off(); };
  }, []);

  const [file, setFile] = React.useState<{ name: string; text: string; rows: number } | null>(null);
  const [columns, setColumns] = React.useState<Record<string, string>>({});
  const [buildingType, setBuildingType] = React.useState<BuildingType>("school");
  const [roomType, setRoomType] = React.useState("small_office");
  const [name, setName] = React.useState("");
  const [cooling, setCooling] = React.useState(false);
  const [hours, setHours] = React.useState({ start: "08:00", end: "17:00" });
  const [spot, setSpot] = React.useState<{ volume?: string; rt?: string; df?: string; radon?: string }>({});
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [label, setLabel] = React.useState<TailLabel | null>(null);
  const [dragging, setDragging] = React.useState(false);
  const svgRef = React.useRef<SVGSVGElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // default hours and cooling per building type (TAIL profiles)
  React.useEffect(() => {
    setCooling(buildingType !== "school");
    if (engineState !== "ready") return;
    engine.hours(buildingType).then((h) => setHours({ start: h.start, end: h.end })).catch(() => {});
  }, [buildingType, engineState]);

  const readFile = async (f: File) => {
    setError(null);
    setLabel(null);
    const text = await f.text();
    setFile({ name: f.name, text, rows: Math.max(0, text.split(/\r?\n/).filter(Boolean).length - 1) });
    try {
      const detected = await engine.detect(text);
      setColumns(Object.fromEntries(Object.entries(detected).map(([k, v]) => [k, v ?? "ignore"])));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const useExample = () => {
    const text = exampleCsv();
    readFile(new File([text], "example-classroom-2024.csv", { type: "text/csv" }));
    setBuildingType("school");
    setName(lang === "da" ? "Eksempelskole, klasse 1.12" : "Example school, room 1.12");
  };

  const hasOutdoor = Object.values(columns).includes("outdoor_temperature");
  const create = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const num = (v?: string) => (v && !Number.isNaN(Number(v.replace(",", "."))) ? Number(v.replace(",", ".")) : undefined);
      const spotValues: Record<string, number> = {};
      if (num(spot.rt) !== undefined && buildingType === "school") spotValues.reverberation_time = num(spot.rt)!;
      if (num(spot.df) !== undefined) spotValues.daylight_factor = num(spot.df)!;
      if (num(spot.radon) !== undefined) spotValues.radon = num(spot.radon)!;
      const result = await engine.rate(file.text, {
        building_type: buildingType,
        room_type: buildingType === "office" ? roomType : null,
        occupied_from: hours.start,
        occupied_to: hours.end,
        mechanical_cooling: cooling ? null : false,
        volume_m3: num(spot.volume) ?? null,
        spot_values: spotValues,
        name: name || null,
      }, columns);
      setLabel(result);
      requestAnimationFrame(() => document.getElementById("label")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const reset = () => { setFile(null); setLabel(null); setColumns({}); setError(null); };
  const columnName = (c: string) =>
    c === "time" ? t.time : c === "ignore" ? t.ignore : c === "outdoor_temperature" ? t.outdoor : t.params[c] ?? c;
  const filename = slugify(name || (lang === "da" ? "tail-maerke" : "tail-label"));

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-card">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between gap-4 px-4 py-4 sm:px-8">
          <a href="https://brunoadam.eu" className="text-foreground" aria-label="baw"><Logo /></a>
          <div className="flex items-center gap-1" role="group" aria-label="Language">
            {(["en", "da"] as const).map((l) => (
              <Button key={l} size="sm" variant={lang === l ? "default" : "ghost"} onClick={() => setLang(l)} aria-pressed={lang === l}>
                {l.toUpperCase()}
              </Button>
            ))}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1200px] px-4 py-10 sm:px-8 sm:py-14">
        <section className="max-w-[720px]">
          <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{t.eyebrow}</div>
          <h1 className="mt-2 font-display text-[34px] font-bold leading-10 tracking-[-0.02em] sm:text-[48px] sm:leading-[52px]">{t.title}</h1>
          <p className="mt-4 text-[18px] leading-7 text-muted-foreground">{t.lead}</p>
          <p className="mt-4 inline-flex items-center gap-2 text-[14px] text-foreground"><Lock className="size-4" aria-hidden /> {t.privacy}</p>
        </section>

        {/* phones: steps, label, details; wide screens: steps and details left, label right */}
        <div className="mt-10 grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
          <div className="flex flex-col gap-6 lg:col-start-1 lg:row-start-1">
            {/* 1 · measurements */}
            <Card>
              <CardHeader>
                <div className="flex items-center gap-3"><Step n={1} active={!file} done={!!file} /><CardTitle>{t.step1}</CardTitle></div>
              </CardHeader>
              <CardContent>
                {!file ? (
                  <div
                    onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) readFile(f); }}
                    className={`flex flex-col items-center gap-3 rounded-md border-2 border-dashed px-6 py-10 text-center transition-colors ${
                      dragging ? "border-primary bg-sunken" : "border-input"}`}
                  >
                    <FileUp className="size-8 text-muted-foreground" aria-hidden />
                    <div className="font-display text-xl font-medium">{t.drop}</div>
                    <p className="max-w-[520px] text-[13px] leading-5 text-muted-foreground">{t.dropHint}</p>
                    <div className="mt-2 flex flex-wrap justify-center gap-2">
                      <Button onClick={() => inputRef.current?.click()}><FileUp aria-hidden /> {t.choose}</Button>
                      <Button variant="quiet" onClick={useExample}>{t.example}</Button>
                    </div>
                    <input ref={inputRef} type="file" accept=".csv,text/csv,text/plain" className="sr-only"
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) readFile(f); e.target.value = ""; }} />
                  </div>
                ) : (
                  <div className="flex flex-col gap-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate font-mono text-[13px]">{file.name}</div>
                        <div className="text-[13px] text-muted-foreground tabular">{formatNumber(file.rows, lang)} {t.rows}</div>
                      </div>
                      <Button size="sm" variant="ghost" onClick={reset}><RotateCcw aria-hidden /> {t.startOver}</Button>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(columns).filter(([, v]) => v !== "ignore").map(([k, v]) => (
                        <Badge key={k} tone={v === "time" ? "neutral" : "info"}>{columnName(v)}</Badge>
                      ))}
                    </div>
                    <Collapsible>
                      <CollapsibleTrigger className="group inline-flex items-center gap-1 text-[14px] font-semibold text-blueprint">
                        {t.columns} ({Object.keys(columns).length}) <ChevronDown className="size-4 transition-transform group-data-[state=open]:rotate-180" />
                      </CollapsibleTrigger>
                      <CollapsibleContent className="mt-3 grid gap-3 sm:grid-cols-2">
                        <p className="text-[13px] text-muted-foreground sm:col-span-2">{t.columnHint}</p>
                        {Object.entries(columns).map(([col, value]) => (
                          <div key={col} className="flex flex-col gap-1.5">
                            <Label className="truncate font-mono text-[12px] font-medium">{col}</Label>
                            <Select value={value} onValueChange={(v) => setColumns((c) => ({ ...c, [col]: v }))}>
                              <SelectTrigger><SelectValue /></SelectTrigger>
                              <SelectContent>
                                {COLUMN_CHOICES.map((c) => <SelectItem key={c} value={c}>{columnName(c)}</SelectItem>)}
                              </SelectContent>
                            </Select>
                          </div>
                        ))}
                      </CollapsibleContent>
                    </Collapsible>
                  </div>
                )}
              </CardContent>
              <CardFooter className="text-[13px] text-muted-foreground">
                {engineState === "loading" && <><Loader2 className="size-4 animate-spin" aria-hidden /> {t.engineLoading}: {t.engineSteps[progress]}…</>}
                {engineState === "ready" && <><span className="size-2 rounded-full bg-success" aria-hidden /> {t.engineReady}</>}
                {engineState === "error" && <><AlertTriangle className="size-4 text-danger" aria-hidden /> {t.error}</>}
              </CardFooter>
            </Card>

            {/* 2 · building */}
            <Card className={!file ? "opacity-60" : undefined}>
              <CardHeader>
                <div className="flex items-center gap-3"><Step n={2} active={!!file && !label} done={!!label} /><CardTitle>{t.step2}</CardTitle></div>
              </CardHeader>
              <CardContent className="flex flex-col gap-5">
                <div className="flex flex-col gap-2">
                  <Label>{t.buildingType}</Label>
                  <Tabs value={buildingType} onValueChange={(v) => setBuildingType(v as BuildingType)}>
                    <TabsList>
                      <TabsTrigger value="office" disabled={!file}><Building2 aria-hidden /> {t.office}</TabsTrigger>
                      <TabsTrigger value="hotel" disabled={!file}><BedDouble aria-hidden /> {t.hotel}</TabsTrigger>
                      <TabsTrigger value="school" disabled={!file}><School aria-hidden /> {t.school}</TabsTrigger>
                    </TabsList>
                  </Tabs>
                  <p className="text-[13px] text-muted-foreground">{t.profiles[buildingType]}</p>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="flex flex-col gap-2 sm:col-span-2">
                    <Label htmlFor="name">{t.name}</Label>
                    <Input id="name" value={name} placeholder={t.namePlaceholder} maxLength={44} disabled={!file} onChange={(e) => setName(e.target.value)} />
                  </div>
                  {buildingType === "office" && (
                    <div className="flex flex-col gap-2">
                      <Label>{t.roomType}</Label>
                      <Select value={roomType} onValueChange={setRoomType} disabled={!file}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="small_office">{t.smallOffice}</SelectItem>
                          <SelectItem value="open_office">{t.openOffice}</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                  <div className="flex flex-col gap-2">
                    <Label>{t.hours}</Label>
                    <div className="flex items-center gap-2">
                      <Input aria-label={t.from} type="time" value={hours.start} disabled={!file} onChange={(e) => setHours((h) => ({ ...h, start: e.target.value }))} />
                      <span className="text-muted-foreground">–</span>
                      <Input aria-label={t.to} type="time" value={hours.end} disabled={!file} onChange={(e) => setHours((h) => ({ ...h, end: e.target.value }))} />
                    </div>
                  </div>
                </div>
                <div className="flex items-start justify-between gap-4 rounded-md border border-line p-4">
                  <div>
                    <Label htmlFor="cooling">{t.cooling}</Label>
                    <p className="mt-1 text-[13px] leading-5 text-muted-foreground">{t.coolingHint}</p>
                    {!cooling && file && !hasOutdoor && (
                      <p className="mt-2 inline-flex items-center gap-1.5 text-[13px] text-signal-ink"><AlertTriangle className="size-4" aria-hidden /> {t.outdoor}?</p>
                    )}
                  </div>
                  <Switch id="cooling" checked={cooling} onCheckedChange={setCooling} disabled={!file} />
                </div>
                <Collapsible>
                  <CollapsibleTrigger disabled={!file} className="group inline-flex items-center gap-1 text-[14px] font-semibold text-blueprint disabled:text-muted-foreground">
                    {t.more} <ChevronDown className="size-4 transition-transform group-data-[state=open]:rotate-180" />
                  </CollapsibleTrigger>
                  <CollapsibleContent className="mt-3 grid gap-4 sm:grid-cols-2">
                    {buildingType === "school" && (
                      <>
                        <div className="flex flex-col gap-2"><Label htmlFor="vol">{t.volume} (m³)</Label>
                          <Input id="vol" inputMode="decimal" value={spot.volume ?? ""} onChange={(e) => setSpot((s) => ({ ...s, volume: e.target.value }))} /></div>
                        <div className="flex flex-col gap-2"><Label htmlFor="rt">{t.rt} (s)</Label>
                          <Input id="rt" inputMode="decimal" value={spot.rt ?? ""} onChange={(e) => setSpot((s) => ({ ...s, rt: e.target.value }))} /></div>
                      </>
                    )}
                    <div className="flex flex-col gap-2"><Label htmlFor="df">{t.df} (%)</Label>
                      <Input id="df" inputMode="decimal" value={spot.df ?? ""} onChange={(e) => setSpot((s) => ({ ...s, df: e.target.value }))} /></div>
                    <div className="flex flex-col gap-2"><Label htmlFor="radon">{t.radon} (Bq/m³)</Label>
                      <Input id="radon" inputMode="decimal" value={spot.radon ?? ""} onChange={(e) => setSpot((s) => ({ ...s, radon: e.target.value }))} /></div>
                  </CollapsibleContent>
                </Collapsible>
              </CardContent>
              <CardFooter>
                <Button variant="signal" size="lg" className="w-full sm:w-auto" disabled={!file || busy || engineState !== "ready"} onClick={create}>
                  {busy ? <><Loader2 className="animate-spin" aria-hidden /> {t.rating}</> : t.create}
                </Button>
              </CardFooter>
            </Card>

            {error && <Alert tone="danger"><AlertTriangle aria-hidden /><div><strong>{t.error}.</strong> {error}</div></Alert>}
          </div>

          {/* 3 · label */}
          <aside id="label" className={`lg:col-start-2 lg:row-start-1 lg:row-span-2 lg:sticky lg:top-6 lg:self-start ${label ? "" : "hidden lg:block"}`}>
            <Card>
              <CardHeader>
                <div className="flex items-center gap-3"><Step n={3} active={!!label} /><CardTitle>{t.step3}</CardTitle></div>
                {!label && <CardDescription>{t.lead.split(".")[0]}.</CardDescription>}
              </CardHeader>
              <CardContent className="flex justify-center">
                {label ? (
                  <TailSticker ref={svgRef} label={label} lang={lang} />
                ) : (
                  <div className="flex aspect-[420/600] w-full max-w-[420px] items-center justify-center rounded-md border border-dashed border-input bg-sunken">
                    <span className="font-display text-[64px] font-bold text-line">TAIL</span>
                  </div>
                )}
              </CardContent>
              {label && (
                <CardFooter className="flex-wrap">
                  <Button onClick={() => svgRef.current && downloadPng(svgRef.current, `${filename}.png`)}><Download aria-hidden /> {t.download} {t.png}</Button>
                  <Button variant="quiet" onClick={() => svgRef.current && downloadSvg(svgRef.current, `${filename}.svg`)}><Download aria-hidden /> {t.svg}</Button>
                </CardFooter>
              )}
            </Card>
          </aside>

          <div className="flex flex-col gap-6 lg:col-start-1 lg:row-start-2">

            {label && (
              <Card>
                <CardHeader><CardTitle>{t.parameters}</CardTitle></CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full text-[14px] tabular">
                    <thead>
                      <tr className="border-b border-line text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
                        <th className="py-2 pr-3 font-semibold">{t.parameter}</th><th className="py-2 pr-3 font-semibold">{t.value}</th>
                        <th className="py-2 text-right font-semibold">{t.ratingCol}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(label.parameters).map(([key, p]) => (
                        <tr key={key} className="border-b border-line last:border-0">
                          <td className="py-2 pr-3">{t.params[key] ?? key}{p.adaptive ? <Badge tone="info" className="ml-2">adaptive</Badge> : null}</td>
                          <td className="py-2 pr-3 font-mono text-[13px] text-muted-foreground">
                            {p.mean != null ? `${formatNumber(p.mean, lang, 1)} ${p.unit ?? ""}` : p.summary_value != null ? `${formatNumber(p.summary_value, lang, 2)} ${p.unit ?? ""}` : "–"}
                          </td>
                          <td className="py-2 text-right"><RatingChip rating={p.rating} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {(label.warnings.length > 0 || Object.keys(label.not_rated).length > 0) && (
                    <div className="mt-4 flex flex-col gap-2">
                      <div className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">{t.warnings}</div>
                      {label.warnings.map((w) => <p key={w} className="text-[13px] text-muted-foreground">{w}</p>)}
                      {Object.entries(label.not_rated).map(([k, why]) => <p key={k} className="text-[13px] text-muted-foreground">{t.params[k] ?? k}: {why}</p>)}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            <section className="max-w-[720px] text-[14px] leading-6 text-muted-foreground">
              <h2 className="font-display text-xl font-medium text-foreground">{t.method}</h2>
              <p className="mt-2">{t.methodText}</p>
            </section>
          </div>

        </div>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-2 px-4 py-6 text-[13px] text-muted-foreground sm:px-8">
          <span>{t.footer}</span>
          <a className="text-blueprint hover:underline" href="https://github.com/baw-dk/hvx">{t.source} · hvx (MPL-2.0)</a>
        </div>
      </footer>
    </div>
  );
}

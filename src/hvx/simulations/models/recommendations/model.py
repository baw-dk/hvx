# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Rule-based recommendations from measured evidence.

Every trigger is a measured share of occupied time against a published limit:

* CO₂ above 1000 ppm (Danish guidance value: Arbejdstilsynet; BR18 § 447 design value
  for teaching rooms).
* Temperature outside the target category's EN 16798-1 range, per season (heating
  season: Category II 20–24 °C; otherwise the cooling-season range, Category II
  23–26 °C), and hours above 26 °C (BR18 guidance value: 100 h per year).
* Relative humidity below 25 % / above 60 % (EN 16798-1 Category II range; humidity
  advice is low priority, as the range is for dimensioning (de)humidification).

A rule fires when the share exceeds 5 % of the season's occupied time (EN 16798-1's
long-term deviation). Priorities are hvx's own judgement: high from 25 %, medium from
10 %, else low (overheating is also high above the BR18 100 h guidance value).

Expected effects are given only where they follow from the room's data with a stated
assumption (see ``hvx.simulations.models.scenario``); they are estimates, not
predictions. Rules that cannot be supported by the data (envelope from correlation
signs, solar heat "savings" in kWh from a default window area, etc.) are not used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import pandas as pd


class RecommendationType(str, Enum):
    """Categories for recommendations shown in the report."""

    VENTILATION = "ventilation"
    SOLAR_SHADING = "solar_shading"
    OVERHEATING = "overheating"
    HEATING = "heating"
    HUMIDITY = "humidity"
    # kept for older JSON consumers
    ENVELOPE = "envelope"
    OPERATIONAL = "operational"
    SEASONAL_CONTROL = "seasonal_control"
    SOLAR_MANAGEMENT = "solar_management"


@dataclass
class SmartRecommendation:
    """Structured recommendation that the report can render."""

    title: str
    type: RecommendationType
    priority: str
    description: str
    expected_benefit: Optional[str] = None
    evidence: Optional[Dict[str, float]] = None
    key: Optional[str] = None  # stable id; selects the text template
    action: Optional[str] = None  # room-independent title, used to group rooms
    summary: Optional[str] = None  # room-independent description for grouped actions
    metric: Optional[float] = None  # numeric effect estimate (see metric_kind)
    metric_kind: Optional[str] = None  # "airflow_factor" | "hours_avoided"

    def as_dict(self) -> dict:
        return {
            "title": self.title,
            "type": self.type.value,
            "priority": self.priority,
            "description": self.description,
            "expected_benefit": self.expected_benefit,
            "evidence": self.evidence or {},
            "key": self.key,
            "action": self.action,
            "summary": self.summary,
            "metric": self.metric,
            "metric_kind": self.metric_kind,
        }


@dataclass
class RoomEvidence:
    """Measured facts a room's recommendations rest on (shares in % of occupied time)."""

    co2_limit: float = 1200.0  # target category limit (ppm)
    heat_band: tuple = (20.0, 24.0)  # target category, heating season
    cool_band: tuple = (23.0, 26.0)  # target category, rest of the year
    co2_share_above_1000: Optional[float] = None
    co2_hours_above_1000: Optional[float] = None
    co2_p95: Optional[float] = None
    heat_share_above: Optional[float] = None
    heat_share_below: Optional[float] = None
    heat_mean: Optional[float] = None
    cool_share_above: Optional[float] = None
    hours_above_26: Optional[float] = None
    hours_above_27: Optional[float] = None
    rh_share_below_25: Optional[float] = None  # heating season
    rh_share_above_60: Optional[float] = None
    airflow_factor: Optional[float] = None
    solar_hours_avoided: Optional[float] = None
    solar_k_per_100: Optional[float] = None
    has_outdoor_temperature: bool = False
    extra: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_frame(
        cls,
        df: pd.DataFrame,
        hours: pd.Series,
        heating: pd.Series,
        co2_limit: float,
        heat_band: tuple,
        cool_band: tuple,
    ) -> "RoomEvidence":
        """``df``: occupied samples; ``hours``: duration of each sample; ``heating``: True in the
        heating season (all aligned on ``df.index``)."""
        ev = cls(co2_limit=co2_limit, heat_band=tuple(heat_band), cool_band=tuple(cool_band))
        heating = heating.reindex(df.index).fillna(False).astype(bool)
        hours = hours.reindex(df.index).fillna(0.0)

        def share(mask: pd.Series, valid: pd.Series) -> Optional[float]:
            total = float(hours[valid].sum())
            return round(100.0 * float(hours[valid & mask].sum()) / total, 1) if total > 0 else None

        if "co2" in df:
            co2 = df["co2"]
            valid = co2.notna()
            if valid.any():
                ev.co2_share_above_1000 = share(co2 > 1000, valid)
                ev.co2_hours_above_1000 = round(float(hours[valid & (co2 > 1000)].sum()), 0)
                ev.co2_p95 = round(float(co2[valid].quantile(0.95)), 0)
        if "temperature" in df:
            t = df["temperature"]
            valid = t.notna()
            h_valid, c_valid = valid & heating, valid & ~heating
            if h_valid.any():
                ev.heat_share_above = share(t > heat_band[1], h_valid)
                ev.heat_share_below = share(t < heat_band[0], h_valid)
                ev.heat_mean = round(float(t[h_valid].mean()), 1)
            if c_valid.any():
                ev.cool_share_above = share(t > cool_band[1], c_valid)
            if valid.any():
                ev.hours_above_26 = round(float(hours[valid & (t > 26.0)].sum()), 0)
                ev.hours_above_27 = round(float(hours[valid & (t > 27.0)].sum()), 0)
        if "humidity" in df:
            rh = df["humidity"]
            valid = rh.notna()
            if (valid & heating).any():
                ev.rh_share_below_25 = share(rh < 25.0, valid & heating)
            if valid.any():
                ev.rh_share_above_60 = share(rh > 60.0, valid)
        ev.has_outdoor_temperature = "outdoor_temperature" in df and df["outdoor_temperature"].notna().any()
        return ev


TRIGGER = 5.0  # % of occupied time (EN 16798-1 long-term deviation)


def _priority(share: Optional[float]) -> str:
    if share is None:
        return "low"
    return "high" if share >= 25.0 else "medium" if share >= 10.0 else "low"


# Texts per language. Placeholders receive numbers already formatted for the language.
RECOMMENDATION_TEXTS: Dict[str, Dict[str, Dict[str, str]]] = {
    "en": {
        "ventilation": {
            "action": "Increase outdoor air during use",
            "title": "Increase outdoor air during use in {room}",
            "description": "CO₂ is above 1000 ppm for {hours} h, {pct} of the occupied time (95th percentile {p95} ppm). "
            "Check that the ventilation runs at its design airflow during use (schedules, dampers, filters), balance "
            "the supply, consider demand-controlled ventilation, and air out the room in breaks.",
            "summary": "CO₂ is above 1000 ppm for a large part of the occupied time. Check that the ventilation runs at "
            "its design airflow during use, balance the supply, consider demand-controlled ventilation, and air out "
            "rooms in breaks.",
            "benefit": "About ×{factor} the outdoor air during use would keep 95 % of the occupied time at or below "
            "{limit} ppm (steady-state estimate).",
        },
        "solar_shading": {
            "action": "Reduce solar heat gains",
            "title": "Reduce solar heat gains in {room}",
            "description": "Outside the heating season the room is above {upper} °C for {pct} of the occupied time and "
            "above 26 °C for {hours} h. Its temperature rises by about {k} °C per 100 W/m² of solar irradiance at equal "
            "outdoor temperature. External shading (blinds, screens, awnings) acts before the heat enters.",
            "summary": "Overheating outside the heating season with a measurable solar contribution. External shading "
            "acts before the heat enters.",
            "benefit": "About {avoided} fewer hours above 26 °C (estimate: shading assumed to remove 70 % of the measured "
            "solar effect).",
        },
        "summer_overheating": {
            "action": "Reduce overheating outside the heating season",
            "title": "Reduce overheating in {room}",
            "description": "Outside the heating season the room is above {upper} °C for {pct} of the occupied time and "
            "above 26 °C for {hours} h (BR18 guidance value: 100 h). Check night and early-morning ventilation, "
            "internal heat sources and solar shading{solar_note}.",
            "summary": "Too warm outside the heating season. Check night and early-morning ventilation, internal heat "
            "sources and solar shading.",
        },
        "heating_overheating": {
            "action": "Lower heating during use",
            "title": "Lower heating during use in {room}",
            "description": "In the heating season the room is above {upper} °C for {pct} of the occupied time (mean "
            "{mean} °C). Check thermostat set-points, the heating curve and whether heating and ventilation work "
            "against each other. This also saves energy.",
            "summary": "Too warm in the heating season. Check thermostat set-points and the heating curve; this also "
            "saves energy.",
        },
        "too_cold": {
            "action": "Raise temperatures in the heating season",
            "title": "Raise temperatures in the heating season in {room}",
            "description": "In the heating season the room is below {lower} °C for {pct} of the occupied time (mean "
            "{mean} °C). Check heat supply and set-points, morning start-up times, supply-air temperature and draughts.",
            "summary": "Too cold in the heating season. Check heat supply and set-points, morning start-up, "
            "supply-air temperature and draughts.",
        },
        "temperature_control": {
            "action": "Stabilise temperature control",
            "title": "Stabilise temperature control in {room}",
            "description": "In the heating season the room is both below {lower} °C ({below} of the occupied time) and "
            "above {upper} °C ({above}). Check thermostat placement and settings, valve balancing, and the interplay of "
            "heating, ventilation and solar gains.",
            "summary": "Both too cold and too warm in the heating season. Check thermostats, valve balancing and the "
            "interplay of heating and ventilation.",
        },
        "dry_air": {
            "action": "Check dry air in winter",
            "title": "Check dry air in winter in {room}",
            "description": "In the heating season relative humidity is below 25 % for {pct} of the occupied time. Dry air "
            "is common with high outdoor-air supply in cold weather; make sure ventilation is not running harder than "
            "needed outside use. Humidification is rarely worthwhile unless occupants complain.",
            "summary": "Dry air in the heating season. Make sure ventilation does not run harder than needed outside "
            "use; humidification is rarely worthwhile.",
        },
        "humid_air": {
            "action": "Check high humidity",
            "title": "Check high humidity in {room}",
            "description": "Relative humidity is above 60 % for {pct} of the occupied time. Check ventilation and moisture "
            "sources; sustained high humidity increases the risk of mould.",
            "summary": "High humidity during use. Check ventilation and moisture sources.",
        },
    },
    "da": {
        "ventilation": {
            "action": "Øg udeluftmængden i brugstiden",
            "title": "Øg udeluftmængden i brugstiden i {room}",
            "description": "CO₂ er over 1000 ppm i {hours} timer, {pct} af brugstiden (95-percentil {p95} ppm). "
            "Kontroller, at ventilationen kører med den projekterede luftmængde i brugstiden (driftstider, spjæld, "
            "filtre), indreguler anlægget, overvej behovsstyret ventilation, og luft ud i pauserne.",
            "summary": "CO₂ er over 1000 ppm i en stor del af brugstiden. Kontroller, at ventilationen kører med den "
            "projekterede luftmængde i brugstiden, indreguler anlægget, overvej behovsstyret ventilation, og luft ud "
            "i pauserne.",
            "benefit": "Ca. ×{factor} udeluft i brugstiden vil holde CO₂ på højst {limit} ppm i 95 % af brugstiden "
            "(skøn ud fra ligevægt).",
        },
        "solar_shading": {
            "action": "Begræns solvarmen",
            "title": "Begræns solvarmen i {room}",
            "description": "Uden for fyringssæsonen er lokalet over {upper} °C i {pct} af brugstiden og over 26 °C i "
            "{hours} timer. Temperaturen stiger ca. {k} °C pr. 100 W/m² solindstråling ved samme udetemperatur. "
            "Udvendig solafskærmning (persienner, screens, markiser) stopper varmen, før den kommer ind.",
            "summary": "Overtemperatur uden for fyringssæsonen med et målbart bidrag fra solen. Udvendig solafskærmning "
            "stopper varmen, før den kommer ind.",
            "benefit": "Ca. {avoided} færre timer over 26 °C (skøn: solafskærmningen antages at fjerne 70 % af den målte "
            "soleffekt).",
        },
        "summer_overheating": {
            "action": "Begræns overtemperatur uden for fyringssæsonen",
            "title": "Begræns overtemperatur i {room}",
            "description": "Uden for fyringssæsonen er lokalet over {upper} °C i {pct} af brugstiden og over 26 °C i "
            "{hours} timer (vejledende værdi i BR18: 100 timer). Kontroller natte- og morgenventilation, interne "
            "varmekilder og solafskærmning{solar_note}.",
            "summary": "For varmt uden for fyringssæsonen. Kontroller natte- og morgenventilation, interne varmekilder "
            "og solafskærmning.",
        },
        "heating_overheating": {
            "action": "Sænk varmen i brugstiden",
            "title": "Sænk varmen i brugstiden i {room}",
            "description": "I fyringssæsonen er lokalet over {upper} °C i {pct} af brugstiden (middel {mean} °C). "
            "Kontroller termostaternes indstilling, varmekurven, og om varme og ventilation modarbejder hinanden. "
            "Det sparer også energi.",
            "summary": "For varmt i fyringssæsonen. Kontroller termostater og varmekurve; det sparer også energi.",
        },
        "too_cold": {
            "action": "Hæv temperaturen i fyringssæsonen",
            "title": "Hæv temperaturen i fyringssæsonen i {room}",
            "description": "I fyringssæsonen er lokalet under {lower} °C i {pct} af brugstiden (middel {mean} °C). "
            "Kontroller varmeforsyning og indstillinger, opstartstid om morgenen, indblæsningstemperatur og træk.",
            "summary": "For koldt i fyringssæsonen. Kontroller varmeforsyning og indstillinger, opstart om morgenen, "
            "indblæsningstemperatur og træk.",
        },
        "temperature_control": {
            "action": "Stabiliser temperaturreguleringen",
            "title": "Stabiliser temperaturreguleringen i {room}",
            "description": "I fyringssæsonen er lokalet både under {lower} °C ({below} af brugstiden) og over {upper} °C "
            "({above}). Kontroller termostaternes placering og indstilling, indregulering af ventiler og samspillet "
            "mellem varme, ventilation og solindfald.",
            "summary": "Både for koldt og for varmt i fyringssæsonen. Kontroller termostater, indregulering og "
            "samspillet mellem varme og ventilation.",
        },
        "dry_air": {
            "action": "Se på tør luft om vinteren",
            "title": "Se på tør luft om vinteren i {room}",
            "description": "I fyringssæsonen er den relative luftfugtighed under 25 % i {pct} af brugstiden. Tør luft er "
            "almindelig ved stor udeluftmængde i koldt vejr; sørg for, at ventilationen ikke kører mere end nødvendigt "
            "uden for brugstiden. Befugtning kan sjældent betale sig, medmindre brugerne klager.",
            "summary": "Tør luft i fyringssæsonen. Sørg for, at ventilationen ikke kører mere end nødvendigt uden for "
            "brugstiden; befugtning kan sjældent betale sig.",
        },
        "humid_air": {
            "action": "Se på høj luftfugtighed",
            "title": "Se på høj luftfugtighed i {room}",
            "description": "Den relative luftfugtighed er over 60 % i {pct} af brugstiden. Kontroller ventilation og "
            "fugtkilder; vedvarende høj fugt øger risikoen for skimmel.",
            "summary": "Høj luftfugtighed i brugstiden. Kontroller ventilation og fugtkilder.",
        },
    },
}
SOLAR_NOTE = {
    "en": " (the solar effect cannot be separated without outdoor temperature data)",
    "da": " (solens bidrag kan ikke adskilles uden målinger af udetemperaturen)",
}


def _number(value: Optional[float], digits: int, language: str) -> str:
    if value is None:
        return "–"
    text = f"{value:,.{digits}f}"
    if language == "da":
        text = text.replace(",", " ").replace(".", ",").replace(" ", ".")
    return text


def _percent(value: Optional[float], digits: int, language: str) -> str:
    sep = " " if language == "da" else ""
    return f"{_number(value, digits, language)}{sep}%"


class SmartRecommendationsModel:
    """Recommendations from :class:`RoomEvidence`; texts in "en" or "da"."""

    def __init__(self, language: str = "en") -> None:
        self.language = language if language in RECOMMENDATION_TEXTS else "en"

    def _make(self, key: str, rec_type: RecommendationType, priority: str, room: str, values: Dict[str, str],
              evidence: Dict[str, Optional[float]], benefit: bool = False, metric: Optional[float] = None,
              metric_kind: Optional[str] = None) -> SmartRecommendation:
        texts = RECOMMENDATION_TEXTS[self.language][key]
        fmt = {"room": room, **values}
        return SmartRecommendation(
            title=texts["title"].format(**fmt),
            type=rec_type,
            priority=priority,
            description=texts["description"].format(**fmt),
            expected_benefit=texts["benefit"].format(**fmt) if benefit and "benefit" in texts else None,
            evidence={k: v for k, v in evidence.items() if v is not None},
            key=key,
            action=texts["action"],
            summary=texts["summary"],
            metric=metric,
            metric_kind=metric_kind,
        )

    def generate(self, room_name: str, ev: RoomEvidence) -> List[SmartRecommendation]:
        lang = self.language
        n = lambda v, d=0: _number(v, d, lang)  # noqa: E731
        pct = lambda v: _percent(v, 0, lang)  # noqa: E731
        recs: List[SmartRecommendation] = []

        # CO₂ during use
        if ev.co2_share_above_1000 is not None and ev.co2_share_above_1000 >= TRIGGER:
            factor = ev.airflow_factor
            recs.append(self._make(
                "ventilation", RecommendationType.VENTILATION, _priority(ev.co2_share_above_1000), room_name,
                {"hours": n(ev.co2_hours_above_1000), "pct": pct(ev.co2_share_above_1000), "p95": n(ev.co2_p95),
                 "factor": n(factor, 1), "limit": n(ev.co2_limit)},
                {"co2_share_above_1000_pct": ev.co2_share_above_1000, "co2_hours_above_1000": ev.co2_hours_above_1000,
                 "co2_p95": ev.co2_p95, "airflow_factor": factor},
                benefit=factor is not None and factor >= 1.05, metric=factor, metric_kind="airflow_factor",
            ))

        # Too warm outside the heating season (one recommendation: solar or general)
        warm = ev.cool_share_above or 0.0
        too_many_hours = (ev.hours_above_26 or 0.0) > 100.0
        if warm >= TRIGGER or too_many_hours:
            priority = "high" if too_many_hours else _priority(warm)
            values = {"upper": n(ev.cool_band[1]), "pct": pct(ev.cool_share_above), "hours": n(ev.hours_above_26),
                      "k": n(ev.solar_k_per_100, 1), "avoided": n(ev.solar_hours_avoided),
                      "solar_note": "" if ev.has_outdoor_temperature else SOLAR_NOTE[lang]}
            evidence = {"cool_share_above_pct": ev.cool_share_above, "hours_above_26": ev.hours_above_26,
                        "hours_above_27": ev.hours_above_27, "solar_k_per_100_w_m2": ev.solar_k_per_100,
                        "solar_hours_avoided": ev.solar_hours_avoided}
            if ev.solar_hours_avoided is not None and ev.solar_hours_avoided >= 10:
                recs.append(self._make("solar_shading", RecommendationType.SOLAR_SHADING, priority, room_name, values,
                                       evidence, benefit=True, metric=ev.solar_hours_avoided, metric_kind="hours_avoided"))
            else:
                recs.append(self._make("summer_overheating", RecommendationType.OVERHEATING, priority, room_name,
                                       values, evidence))

        # Heating season: too cold, too warm, or both
        above, below = ev.heat_share_above or 0.0, ev.heat_share_below or 0.0
        heat_values = {"upper": n(ev.heat_band[1]), "lower": n(ev.heat_band[0]), "mean": n(ev.heat_mean, 1),
                       "above": pct(ev.heat_share_above), "below": pct(ev.heat_share_below)}
        heat_evidence = {"heat_share_above_pct": ev.heat_share_above, "heat_share_below_pct": ev.heat_share_below,
                         "heat_mean": ev.heat_mean}
        if above >= TRIGGER and below >= TRIGGER:
            recs.append(self._make("temperature_control", RecommendationType.HEATING, _priority(max(above, below)),
                                   room_name, heat_values, heat_evidence))
        elif below >= TRIGGER:
            recs.append(self._make("too_cold", RecommendationType.HEATING, _priority(below), room_name,
                                   {**heat_values, "pct": pct(below)}, heat_evidence))
        elif above >= TRIGGER:
            recs.append(self._make("heating_overheating", RecommendationType.HEATING, _priority(above), room_name,
                                   {**heat_values, "pct": pct(above)}, heat_evidence))

        # Humidity: information, low priority
        if ev.rh_share_below_25 is not None and ev.rh_share_below_25 >= 20.0:
            recs.append(self._make("dry_air", RecommendationType.HUMIDITY, "low", room_name,
                                   {"pct": pct(ev.rh_share_below_25)}, {"rh_share_below_25_pct": ev.rh_share_below_25}))
        if ev.rh_share_above_60 is not None and ev.rh_share_above_60 >= 10.0:
            recs.append(self._make("humid_air", RecommendationType.HUMIDITY, "medium" if ev.rh_share_above_60 >= 25 else "low",
                                   room_name, {"pct": pct(ev.rh_share_above_60)}, {"rh_share_above_60_pct": ev.rh_share_above_60}))

        order = {"high": 0, "medium": 1, "low": 2}
        return sorted(recs, key=lambda r: order.get(r.priority, 3))


__all__ = ["SmartRecommendationsModel", "SmartRecommendation", "RecommendationType", "RoomEvidence", "RECOMMENDATION_TEXTS"]

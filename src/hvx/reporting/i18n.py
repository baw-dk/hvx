# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Report translations.

Messages are keyed by their English text (gettext style): English needs no
catalog, and a missing translation falls back to English instead of failing.
Placeholders receive values already formatted for the language
(:meth:`Translator.num`, :meth:`Translator.pct`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

LANGUAGES = ("en", "da")
NBSP = " "

CATALOG: Dict[str, Dict[str, str]] = {
    "da": {
        # --- page chrome and sections
        "Indoor environmental quality report": "Indeklimarapport",
        "IEQ report": "indeklimarapport",
        "Target: EN 16798-1 Category {cat}": "Mål: EN 16798-1 kategori {cat}",
        "Assessed: {hours}": "Vurderet: {hours}",
        "Generated {date}": "Udarbejdet {date}",
        "Key figures": "Nøgletal",
        "IEQ score (0–100)": "Indeklimascore (0–100)",
        "Rooms meeting Category {cat}": "Lokaler der opfylder kategori {cat}",
        "Portfolio category ({pct}% rule)": "Samlet kategori ({pct} %-regel)",
        "Rooms analysed ({pct} coverage)": "Analyserede lokaler ({pct} dækning)",
        "Buildings": "Bygninger",
        "Key findings": "Hovedresultater",
        "Portfolio overview": "Overblik",
        "Rooms by achieved category": "Lokaler fordelt på opnået kategori",
        "Average hours per room above limits (occupied time)": "Gennemsnitligt antal timer pr. lokale over grænseværdier (brugstid)",
        "Time within Category {cat} limits": "Andel af tiden inden for kategori {cat}",
        "No parameter data.": "Ingen måledata.",
        "Distribution of room IEQ scores": "Fordeling af lokalernes indeklimascore",
        "Each bar counts rooms by composite score (0 = never within limits, 100 = always).":
            "Søjlerne viser antal lokaler pr. scoreinterval (0 = aldrig inden for grænserne, 100 = altid).",
        "Priority actions": "Prioriterede tiltag",
        "Priority": "Prioritet",
        "Action": "Tiltag",
        "Rooms": "Lokaler",
        "Where": "Hvor",
        "Expected benefit (worst case)": "Forventet effekt (værste lokale)",
        "and {n} more": "og {n} flere",
        "Building": "Bygning",
        "Category": "Kategori",
        "Meets target": "Opfylder mål",
        "Score": "Score",
        "Temp.": "Temp.",
        "RH": "RF",
        "Category mix": "Kategorifordeling",
        "Average hours per room above 1000 ppm during occupied time": "Gennemsnitligt antal timer pr. lokale over 1000 ppm i brugstiden",
        "Rooms needing attention": "Lokaler der kræver opmærksomhed",
        "The {n} room(s) furthest from the Category {cat} target, worst first.":
            "De {n} lokaler der ligger længst fra målet om kategori {cat}, det dårligste først.",
        "Parameter": "Parameter",
        "Within Cat {cat}": "Inden for kat. {cat}",
        "Mean": "Middel",
        "Min": "Min.",
        "Max": "Maks.",
        "By season": "Pr. sæson",
        "{season} {cat} ({pct} within target)": "{season} {cat} ({pct} inden for målet)",
        "Hours above limits (occupied)": "Timer over grænseværdier (brugstid)",
        "By time of day": "Pr. tidspunkt",
        "{period}: CO₂ mean {mean}, > 1000 ppm {pct} of the time": "{period}: CO₂ middel {mean}, over 1000 ppm {pct} af tiden",
        "Air change from CO₂ decay": "Luftskifte beregnet ud fra CO₂-henfald",
        "Decays mostly occur after hours, when mechanical ventilation may be off.":
            "Henfaldene sker mest efter brugstid, hvor den mekaniske ventilation kan være slukket.",
        "{n} recommendation(s)": "{n} anbefaling(er)",
        "Benefit": "Effekt",
        "Data: {n} samples, {start} → {end}, {pct} complete": "Data: {n} målinger, {start} → {end}, {pct} komplet",
        "{n} gap(s)": "{n} hul(ler)",
        "Notes": "Bemærkninger",
        "All rooms": "Alle lokaler",
        "Show all {n} rooms": "Vis alle {n} lokaler",
        "Filter rooms, buildings, categories…": "Filtrer lokaler, bygninger, kategorier …",
        "Filter rooms": "Filtrer lokaler",
        "Floor": "Etage",
        "Room": "Lokale",
        "Data": "Data",
        "no data": "ingen data",
        "error": "fejl",
        "Data coverage": "Datadækning",
        "{n} room(s) were not assessed:": "{n} lokale(r) kunne ikke vurderes:",
        "… and {n} more (see JSON/CSV export).": "… og {n} flere (se JSON/CSV-udtræk).",
        "Method": "Metode",
        "built in {s} s": "genereret på {s} s",
        "rooms": "lokaler",
        "pass": "opfyldt",
        "fail": "ikke opfyldt",
        "Below Category IV": "Under kategori IV",
        "Not rated": "Ikke vurderet",
        "Cat {cat}": "Kat. {cat}",
        "High": "Høj",
        "Medium": "Middel",
        "Low": "Lav",
        "Introduction": "Indledning",
        "CO₂ above 1000 ppm by time of day": "CO₂ over 1000 ppm pr. time på dagen",
        "CO₂ above 1000 ppm by month": "CO₂ over 1000 ppm pr. måned",
        "Share of occupied time above 1000 ppm, for the rooms needing attention and each building.":
            "Andel af brugstiden over 1000 ppm for de lokaler, der kræver opmærksomhed, og for hver bygning.",
        "Hours above 26 °C by month": "Timer over 26 °C pr. måned",
        "Occupied hours above 26 °C, for the rooms needing attention and each building (building rows: average per room).":
            "Timer over 26 °C i brugstiden for de lokaler, der kræver opmærksomhed, og for hver bygning (bygningsrækker: gennemsnit pr. lokale).",
        "Building average": "Gns. for bygningen",
        "Time patterns": "Mønstre over døgn og år",
        "TAIL rating": "TAIL-vurdering",
        "{n} rooms": "{n} lokaler",
        "not assessed": "ikke vurderet",
        "not measured": "ikke målt",
        "Typical room": "Typisk lokale",
        "Overall": "Samlet",
        "Badges: the typical room. Bars below: how the rooms are spread over I–IV.":
            "Mærkerne viser det typiske lokale; bjælkerne under dem, hvordan lokalerne fordeler sig på I–IV.",
        "Report prepared by": "Rapport udarbejdet af",
        "CVR no. {cvr}": "CVR-nr. {cvr}",
        "TAIL rates Thermal, Acoustic, Indoor air and Luminous conditions from I (best) to IV. Read the tree from left to right: each domain takes its worst parameter and the overall rating its worst domain. For a group of rooms each parameter shows the typical room (rounded mean of the rooms' ratings). Grey, dashed: not measured, so the domain is not rated.":
            "TAIL vurderer det termiske (T), akustiske (A), luftkvaliteten (I) og lysforholdene (L) fra I (bedst) til IV. Træet læses fra venstre mod højre: et domæne får sin dårligste parameter og den samlede vurdering det dårligste domæne. For en gruppe lokaler viser hver parameter det typiske lokale (afrundet gennemsnit af lokalernes vurdering). Grå, stiplet: ikke målt, så domænet vurderes ikke.",
        # --- method section
        "<strong>Standard.</strong> Rooms are assessed with EN 16798-1 (plus TAIL and BR18 where applicable). Each parameter reaches the best category whose limits it meets in at least 95 % of its measured occupied hours, and the room takes its worst parameter; Category IV is anything outside Category III. CO₂ limits are 550/800/1350 ppm above an assumed outdoor level of 400 ppm (950/1200/1750 ppm). Relative humidity is reported but counts towards the category only in rooms with humidity control, because EN 16798-1 gives humidity criteria for dimensioning (de)humidification.":
            "<strong>Standard.</strong> Lokalerne vurderes efter DS/EN 16798-1 (samt TAIL og BR18, hvor de er relevante). Hver parameter opnår den bedste kategori, hvis grænser den overholder i mindst 95 % af de målte brugstimer, og lokalet får sin dårligste parameter; kategori IV er alt uden for kategori III. CO₂-grænserne er 550/800/1350 ppm over et antaget udeniveau på 400 ppm (950/1200/1750 ppm). Den relative luftfugtighed vises, men tæller kun med i kategorien i lokaler med fugtstyring, da DS/EN 16798-1 angiver fugtkriterier til dimensionering af befugtning og affugtning.",
        "<strong>Outside the heating season</strong> the fixed cooling-season ranges are used (Category II 23–26 °C). They assume a cooled building; for buildings without mechanical cooling EN 16798-1 uses the adaptive model, which needs outdoor temperature and the room's ventilation type (natural or mixed). Rooms that are too cool in summer by these ranges may be comfortable by the adaptive model.":
            "<strong>Uden for fyringssæsonen</strong> bruges de faste intervaller for kølesæsonen (kategori II 23–26 °C). De forudsætter en bygning med køling; for bygninger uden mekanisk køling bruger DS/EN 16798-1 den adaptive model, som kræver udetemperatur og lokalets ventilationsform (naturlig eller hybrid). Lokaler, der efter disse intervaller er for kølige om sommeren, kan være komfortable efter den adaptive model.",
        "<strong>Seasons.</strong> Data is split into the country's heating and cooling months; each part is assessed with its own criteria, and a room's category is its worst seasonal category.":
            "<strong>Sæsoner.</strong> Data deles i fyringssæson (oktober–april) og sommerhalvår (maj–september); hver del vurderes med sine egne kriterier, og lokalets kategori er den dårligste af de to.",
        "<strong>Seasons.</strong> All data is assessed with {season} criteria.":
            "<strong>Sæson.</strong> Alle data vurderes med kriterierne for {season}.",
        "<strong>Assessed hours.</strong> Standards are applied to occupied hours only ({hours}); the air-change estimate uses all hours. Hours above limits are weighted by each sample's duration.":
            "<strong>Vurderet tid.</strong> Standarderne anvendes kun på brugstiden ({hours}); luftskiftet beregnes ud fra alle timer. Timer over grænseværdier vægtes med hver målings varighed.",
        "<strong>Assessed hours.</strong> All hours are assessed.":
            "<strong>Vurderet tid.</strong> Alle timer indgår.",
        "<strong>Compliance %.</strong> Share of samples within Category {cat} limits, per parameter. Parameters below {pct} are listed as issues.":
            "<strong>Overholdelse i %.</strong> Andel af målingerne inden for kategori {cat}-grænserne pr. parameter. Parametre under {pct} nævnes som problemer.",
        "<strong>IEQ score.</strong> Weighted mean of parameter compliance ({weights}; weights renormalised over available parameters).":
            "<strong>Indeklimascore.</strong> Vægtet gennemsnit af overholdelsen pr. parameter ({weights}; vægtene fordeles på de målte parametre).",
        "<strong>Building and portfolio category.</strong> An hvx summary, not part of EN 16798-1: the best category that at least {pct} of rated rooms reach. Building and portfolio averages are area-weighted when every room has a floor area.":
            "<strong>Bygningens og den samlede kategori.</strong> En opsummering i hvx, ikke en del af DS/EN 16798-1: den bedste kategori, som mindst {pct} af de vurderede lokaler opnår. Gennemsnit er arealvægtede, når alle lokaler har et areal.",
        "<strong>Identifiers.</strong> Brick classes and IFC GlobalIds for every room are in the JSON and CSV exports.":
            "<strong>Identifikation.</strong> Brick-klasser og IFC GlobalId for alle lokaler findes i JSON- og CSV-udtrækket.",
        # --- parameters, seasons, periods
        "Temperature": "Temperatur",
        "CO₂": "CO₂",
        "Humidity": "Luftfugtighed",
        "winter": "fyringssæson",
        "summer": "sommerhalvår",
        "all_year": "hele året",
        "Winter": "Fyringssæson",
        "Summer": "Sommerhalvår",
        "Full year ({seasons})": "Hele året ({seasons})",
        "morning": "formiddag",
        "afternoon": "eftermiddag",
        "evening": "aften",
        # --- generated issues and messages
        "Achieves Category {cat}; target is Category {target}.": "Opnår kategori {cat}; målet er kategori {target}.",
        "Below EN 16798 Category IV ({seasons}); target is Category {target}.":
            "Under EN 16798 kategori IV ({seasons}); målet er kategori {target}.",
        "assessed period": "vurderet periode",
        "BR18 not met: {rules}.": "BR18 ikke opfyldt: {rules}.",
        "{label} within Category {target} limits only {pct} of the time{suffix}.":
            "{label} inden for kategori {target}-grænserne kun {pct} af tiden{suffix}.",
        "mean {value}": "middel {value}",
        "peak {value}": "maks. {value}",
        "range {low}–{high}": "interval {low}–{high}",
        "CO₂ above {limit} ppm for {hours} h{share}.": "CO₂ over {limit} ppm i {hours} timer{share}.",
        " ({pct} of occupied time)": " ({pct} af brugstiden)",
        "Above 26 °C for {hours} h in use (BR18 allows 100 h).": "Over 26 °C i {hours} timer i brugstiden (BR18 tillader 100 timer).",
        "Above 27 °C for {hours} h in use (BR18 allows 25 h).": "Over 27 °C i {hours} timer i brugstiden (BR18 tillader 25 timer).",
        "No sensor data": "Ingen måledata",
        "No usable sensor data": "Ingen brugbare måledata",
        "No data during occupied hours ({hours})": "Ingen data i brugstiden ({hours})",
        "{season}: not enough data in season ({n} samples); skipped.": "{season}: for få data i sæsonen ({n} målinger); udeladt.",
        # BR18 rule names (standards/br18/config.yaml)
        "Educational spaces CO2 limit": "CO₂-grænse i undervisningsrum (§ 447, stk. 2)",
        "Non-residential operative temperature ≤26°C": "Operativ temperatur højst 26 °C (højst 100 timer)",
        "Non-residential operative temperature ≤27°C": "Operativ temperatur højst 27 °C (højst 25 timer)",
        # --- key findings
        "{n} of {total} rooms analysed ({pct} coverage)": "{n} af {total} lokaler analyseret ({pct} dækning)",
        ", {area} m²": ", {area} m²",
        "{pct} of rated rooms meet the Category {cat} target.": "{pct} af de vurderede lokaler opfylder målet om kategori {cat}.",
        "Portfolio category {cat}: at least {pct} of rooms reach Category {cat} or better.":
            "Samlet kategori {cat}: mindst {pct} af lokalerne opnår kategori {cat} eller bedre.",
        "{label} is the weakest parameter: rooms are within Category {cat} limits {pct} of the time on average.":
            "{label} er den svageste parameter: lokalerne er i gennemsnit inden for kategori {cat}-grænserne {pct} af tiden.",
        "Rooms are above 1000 ppm CO₂ for {hours} occupied hours on average": "Lokalerne er i gennemsnit over 1000 ppm CO₂ i {hours} timer af brugstiden",
        " and above 2000 ppm for {hours} hours": " og over 2000 ppm i {hours} timer",
        "Rooms are above 26 °C for {hours} occupied hours on average (BR18 allows 100 h).":
            "Lokalerne er i gennemsnit over 26 °C i {hours} timer af brugstiden (BR18 tillader 100 timer).",
        "Lowest-scoring building: {name} (IEQ score {score}).": "Bygningen med lavest score: {name} (indeklimascore {score}).",
        "{n} room(s) could not be assessed ({no_data} without data, {failed} failed).":
            "{n} lokale(r) kunne ikke vurderes ({no_data} uden data, {failed} med fejl).",
        # building and room types
        "school": "skole",
        "education": "uddannelse",
        "office": "kontor",
        "residential": "bolig",
        "classroom": "klasselokale",
        "meeting_room": "mødelokale",
        "open_office": "storrumskontor",
        "private_office": "kontor",
        # --- schedule descriptions
        "all hours (24/7 occupancy)": "alle timer (døgnbrug)",
        "{days} {start}–{end}": "{days} kl. {start}–{end}",
        ", excluding public holidays": ", ekskl. helligdage",
        " and {n} holiday period(s)": " og {n} ferieperiode(r)",
    }
}

WEEKDAYS = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "da": ["man", "tir", "ons", "tor", "fre", "lør", "søn"],
}
MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "da": ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"],
}


class Translator:
    """Translate and format for one language."""

    def __init__(self, language: str = "en") -> None:
        self.language = language if language in LANGUAGES else "en"

    def __call__(self, msgid: str, **params) -> str:
        text = CATALOG.get(self.language, {}).get(msgid, msgid)
        return text.format(**params) if params else text

    # numbers ----------------------------------------------------------------
    def num(self, value: Optional[float], digits: int = 1, unit: str = "") -> str:
        if value is None:
            return "–"
        text = f"{value:,.{digits}f}"
        if self.language == "da":
            text = text.replace(",", NBSP).replace(".", ",").replace(NBSP, ".")
        return f"{text}{NBSP}{unit}" if unit else text

    def pct(self, value: Optional[float], digits: int = 1) -> str:
        if value is None:
            return "–"
        return f"{self.num(value, digits)}{NBSP}%" if self.language == "da" else f"{self.num(value, digits)}%"

    def date(self, value: Optional[str]) -> str:
        if not value:
            return "–"
        try:
            d = datetime.fromisoformat(value)
        except ValueError:
            return value
        return d.strftime("%d.%m.%Y") if self.language == "da" else d.strftime("%Y-%m-%d")

    def weekday(self, index: int) -> str:
        return WEEKDAYS[self.language][index]

    def month(self, index: int) -> str:
        """``index`` 1–12."""
        return MONTHS[self.language][index - 1]


def describe_schedule(schedule, t: Translator) -> str:
    """Localised :meth:`OccupancySchedule.describe`."""
    if schedule.always:
        return t("all hours (24/7 occupancy)")
    days = ", ".join(t.weekday(d) for d in schedule.weekdays)
    if tuple(schedule.weekdays) == (0, 1, 2, 3, 4):
        days = f"{t.weekday(0)}–{t.weekday(4)}"
    text = t("{days} {start}–{end}", days=days, start=schedule.start, end=schedule.end)
    if schedule.public_holidays:
        text += t(", excluding public holidays")
    if schedule.holiday_periods:
        text += t(" and {n} holiday period(s)", n=len(schedule.holiday_periods))
    return text


__all__ = ["Translator", "LANGUAGES", "CATALOG", "describe_schedule"]

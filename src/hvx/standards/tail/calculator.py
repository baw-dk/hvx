# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
TAIL (Thermal, Acoustic, Indoor air quality, Luminous) rating calculator.

Follows the authors' reference implementation ``tail.R``
(github.com/asitkm76/TAILRatingScheme, commit c71b8b5) of Wargocki et al.
(2021), Energy & Buildings 244, 111029, doi:10.1016/j.enbuild.2021.111029.
"l.NN" in comments is a line of ``tail.R``. Every threshold is read from
``config.yaml`` next to this module, which cites the same lines.

How each parameter is labelled (details in config.yaml):

* temperature and relative humidity: each occupied sample is coloured
  Green/Yellow/Orange/Red and the label follows from the time shares of the
  colours (l.351-369, 450-470). Temperature uses heating-season bands for
  samples in October-May and non-heating bands for June-September, per sample.
* CO2: 95th percentile after raising values below outdoor (420 ppm) to outdoor.
* noise: 5th percentile after raising values below 30 dB to 30 dB.
* illuminance: share of time within 300-500 lx (offices) or at or above
  100 lx (hotels).
* PM2.5, formaldehyde, benzene, radon: any Red sample -> IV, any Yellow -> II, else I.
* ventilation, mould, daylight factor: worst observation.
* domain = worst parameter, overall = worst domain; unmeasured and unrated
  parameters are left out.

Where hvx departs from a literal reading of tail.R:

* The time-share rule of tail.R has gaps (e.g. 99.5 % Green + 0.5 % Red meets
  none of the I-III conditions and falls to IV). hvx reads it cumulatively:
  I if Green >= 94 %, Orange <= 1 % and Red = 0; otherwise II if Orange <= 5 %
  and Red <= 1 %; otherwise III if Red <= 5 %; otherwise IV. Every case
  tail.R rates I-III keeps its label.
* Shares are over samples that have a value; tail.R counts missing values
  in the denominator.
* tail.R leaves a hotel noise P5 of exactly 35 dB without category; hvx rates it
  Orange. RH and illuminance of building types other than office and hotel use
  the office rules (tail.R leaves them unrated).
* PM10 and VOC are not TAIL parameters. They are rated with hvx's own limits
  as *extensions* and never enter the Indoor Air domain or the overall rating.

tail.R rates a whole building by pooling the data of all monitored rooms; this
calculator rates whatever series it is given (one room in hvx reports).
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

import numpy as np
import pandas as pd
import yaml

from hvx.core.schedules import (
    generate_occupancy_mask,
    get_opening_profile_for_building_type,
)

COLORS: Tuple[str, ...] = ("green", "yellow", "orange", "red")


@lru_cache(maxsize=1)
def _load_config_cached() -> Dict[str, Any]:
    with open(Path(__file__).with_name("config.yaml"), encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_config() -> Dict[str, Any]:
    """The TAIL configuration (a copy: callers may modify it)."""
    return copy.deepcopy(_load_config_cached())


def _deep_merge(base: Dict[str, Any], overrides: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in (overrides or {}).items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def normalize_type(value: Any) -> str:
    """'Small office', 'small-office', RoomType.OPEN_OFFICE -> 'small_office', 'open_office'."""
    value = getattr(value, "value", value)
    if value is None:
        return ""
    return re.sub(r"[\s\-]+", "_", str(value).strip().lower())


def r_round(series: pd.Series, digits: int) -> pd.Series:
    """
    Round like R's ``round()`` (R >= 4): to the nearest decimal of the value's
    exact binary representation, exact halves to even. Python's ``round`` does
    the same; numpy's ``round`` does not (``np.round(23.05, 1)`` is 23.0, R and
    Python give 23.1).
    """
    return series.map(lambda v: float(round(float(v), digits)))


class TAILRating(int, Enum):
    """TAIL labels (tail.R l.655-671)."""

    EXCELLENT = 1  # I, Green
    GOOD = 2  # II, Yellow
    FAIR = 3  # III, Orange
    POOR = 4  # IV, Red

    def to_label(self) -> str:
        """Convert to roman numeral label."""
        return {1: "I", 2: "II", 3: "III", 4: "IV"}[self.value]

    def to_color(self) -> str:
        """Get color name for rating."""
        return {1: "Green", 2: "Yellow", 3: "Orange", 4: "Red"}[self.value]

    @classmethod
    def from_label(cls, label: str) -> "TAILRating":
        return cls({"I": 1, "II": 2, "III": 3, "IV": 4}[label])


class TAILCategory(str, Enum):
    """TAIL domains."""

    THERMAL = "thermal"
    ACOUSTIC = "acoustic"
    IAQ = "iaq"  # Indoor Air Quality
    LUMINOUS = "luminous"


@dataclass
class TAILParameterResult:
    """Result for a single parameter."""

    parameter: str
    category: TAILCategory
    rating: TAILRating
    rating_label: str
    dominant_color: str
    distribution: Dict[str, float]
    sample_count: int
    summary_value: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    extension: bool = False  # hvx extension (PM10, VOC): not a TAIL parameter


@dataclass
class TAILCategoryResult:
    """Result for a TAIL domain."""

    category: TAILCategory
    rating: TAILRating
    rating_label: str
    compliance_rate: float
    parameter_count: int
    parameters: List[TAILParameterResult]
    dominant_color: str


@dataclass
class TAILOverallResult:
    """Overall TAIL assessment result. ``overall_rating`` is None when nothing could be rated."""

    overall_rating: Optional[TAILRating]
    overall_rating_label: Optional[str]
    overall_compliance_rate: float
    categories: Dict[TAILCategory, TAILCategoryResult]
    total_parameters: int
    visualization: Dict[str, Any]
    parameter_results: List[TAILParameterResult]
    extensions: List[TAILParameterResult] = field(default_factory=list)
    not_rated: Dict[str, str] = field(default_factory=dict)  # parameter -> why it was not rated
    profile: str = "office"  # building-type profile used: office, hotel or school


Outcome = Union[TAILParameterResult, str, None]  # result, reason for not rating, or no data


class TAILCalculator:
    """
    Calculator for the TAIL rating scheme (see module docstring).

    ``assess_timeseries`` filters to the building type's opening hours unless the
    caller says the data is already restricted to occupied hours
    (``occupancy_filtered=True``, as the report pipeline does).
    """

    COLOR_ORDER = list(COLORS)
    COLOR_TO_RATING = {
        "green": TAILRating.EXCELLENT,
        "yellow": TAILRating.GOOD,
        "orange": TAILRating.FAIR,
        "red": TAILRating.POOR,
    }

    # Sensor names -> TAIL parameter (matched after lower-casing and removing spaces/underscores)
    PARAMETER_ALIASES = {
        "temp": "temperature",
        "temperature": "temperature",
        "operativetemperature": "temperature",
        "rh": "relative_humidity",
        "relativehumidity": "relative_humidity",
        "humidity": "relative_humidity",
        "co2": "co2",
        "co₂": "co2",
        "pm25": "pm25",
        "pm2.5": "pm25",
        "pm10": "pm10",
        "voc": "voc",
        "tvoc": "voc",
        "formaldehyde": "formaldehyde",
        "ch2o": "formaldehyde",
        "hcho": "formaldehyde",
        "benzene": "benzene",
        "radon": "radon",
        "ventilation": "ventilation",
        "vent": "ventilation",
        "mold": "mold",
        "mould": "mold",
        "noise": "noise",
        "noiselevel": "noise",
        "sound": "noise",
        "soundlevel": "noise",
        "soundpressure": "noise",
        "illuminance": "illuminance",
        "lux": "illuminance",
        "light": "illuminance",
        "daylightfactor": "daylight_factor",
        "df": "daylight_factor",
        "no2": "no2",
        "nitrogendioxide": "no2",
        "reverberationtime": "reverberation_time",
        "rt": "reverberation_time",
        "t20": "reverberation_time",
        "t30": "reverberation_time",
    }

    PARAMETER_CATEGORIES = {
        "temperature": TAILCategory.THERMAL,
        "relative_humidity": TAILCategory.IAQ,
        "co2": TAILCategory.IAQ,
        "pm25": TAILCategory.IAQ,
        "formaldehyde": TAILCategory.IAQ,
        "benzene": TAILCategory.IAQ,
        "radon": TAILCategory.IAQ,
        "ventilation": TAILCategory.IAQ,
        "mold": TAILCategory.IAQ,
        "noise": TAILCategory.ACOUSTIC,
        "illuminance": TAILCategory.LUMINOUS,
        "daylight_factor": TAILCategory.LUMINOUS,
        # school profile only (Tran 2024); elsewhere NO2 is an extension and RT is not rated
        "no2": TAILCategory.IAQ,
        "reverberation_time": TAILCategory.ACOUSTIC,
    }
    PROFILE_ONLY = ("no2", "reverberation_time")
    # Not TAIL parameters: rated as hvx extensions, outside the domains (config.yaml `extensions`)
    EXTENSION_CATEGORIES = {"pm10": TAILCategory.IAQ, "voc": TAILCategory.IAQ, "no2": TAILCategory.IAQ}

    # ------------------------------------------------------------------ public API
    @classmethod
    def config(cls, overrides: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        """config.yaml, with ``overrides`` deep-merged into its ``parameters`` section."""
        cfg = load_config()
        if overrides:
            cfg["parameters"] = _deep_merge(cfg.get("parameters") or {}, overrides)
        return cfg

    @classmethod
    def assess_instant_values(
        cls,
        measured_values: Dict[str, float],
        thresholds: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TAILOverallResult:
        """Score a snapshot of measurements (one sample per parameter, no timestamps)."""
        series_data = {param: pd.Series([value]) for param, value in measured_values.items()}
        return cls.assess_timeseries(series_data, thresholds, metadata=metadata, occupancy_filtered=True)

    @classmethod
    def assess_timeseries(
        cls,
        timeseries_data: Dict[str, pd.Series],
        thresholds: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        building_name: Optional[str] = None,
        occupancy_filtered: Optional[bool] = None,
    ) -> TAILOverallResult:
        """
        Rate time series following tail.R.

        Args:
            timeseries_data: ``{sensor name: Series}``, ideally with a DatetimeIndex.
                Timezone-aware indexes are converted to the building's local time
                (``metadata["timezone"]``, else the timestamps' own offset).
            thresholds: optional overrides deep-merged into config.yaml's
                ``parameters`` (e.g. ``{"co2": {"outdoor_ppm": 400}}``).
            metadata: ``building_type``, ``room_type``, ``area_m2``,
                ``design_occupancy`` (persons), ``timezone``, ``outdoor_co2_ppm``,
                ``season_hint`` ("heating"/"non_heating", only used without timestamps).
            occupancy_filtered: True when the data is already restricted to
                occupied hours; otherwise the building type's opening hours are
                applied. Defaults to ``metadata["occupancy_filtered"]``.
        """
        metadata = dict(metadata or {})
        if occupancy_filtered is None:
            occupancy_filtered = bool(metadata.get("occupancy_filtered", False))
        cfg = cls.config(thresholds)
        profile_name, profile = cls.profile_for(metadata.get("building_type"), cfg)
        if profile.get("parameters"):
            cfg["parameters"] = _deep_merge(cfg["parameters"], profile["parameters"])
            if thresholds:  # caller overrides still win over the profile
                cfg["parameters"] = _deep_merge(cfg["parameters"], thresholds)
        metadata.setdefault("profile", profile_name)
        if profile.get("default_room_type") and not metadata.get("room_type"):
            metadata["room_type"] = profile["default_room_type"]
        prepared = cls._prepare_series(timeseries_data, metadata, occupancy_filtered)

        parameter_results: List[TAILParameterResult] = []
        extensions: List[TAILParameterResult] = []
        not_rated: Dict[str, str] = {}
        seen = set()
        for param_name, series in prepared.items():
            normalized = cls._normalize_parameter_name(param_name)
            if normalized in seen:
                continue
            if normalized in cls.PROFILE_ONLY and normalized not in cfg["parameters"]:
                if normalized in cls.EXTENSION_CATEGORIES:
                    outcome = cls._evaluate_extension(normalized, series, cfg)
                else:
                    outcome = f"Not rated: {normalized} is part of the TAIL scheme for schools only."
            elif normalized in cls.PARAMETER_CATEGORIES:
                evaluator = cls._get_parameter_evaluator(normalized)
                outcome = evaluator(series, metadata, cfg)
            elif normalized in cls.EXTENSION_CATEGORIES:
                outcome = cls._evaluate_extension(normalized, series, cfg)
            else:
                continue
            seen.add(normalized)
            if isinstance(outcome, str):
                not_rated[normalized] = outcome
            elif outcome is not None:
                (extensions if outcome.extension else parameter_results).append(outcome)

        category_results = cls._build_category_results(parameter_results)
        overall_rating, overall_compliance = cls._summarize_overall(category_results)
        visualization = cls._build_visualization(
            parameter_results=parameter_results,
            category_results=category_results,
            overall_rating=overall_rating,
            overall_compliance=overall_compliance,
            metadata=metadata,
            building_name=building_name,
            extensions=extensions,
            not_rated=not_rated,
        )
        return TAILOverallResult(
            overall_rating=overall_rating,
            overall_rating_label=overall_rating.to_label() if overall_rating else None,
            overall_compliance_rate=round(overall_compliance, 2),
            categories=category_results,
            total_parameters=len(parameter_results),
            visualization=visualization,
            parameter_results=parameter_results,
            extensions=extensions,
            not_rated=not_rated,
            profile=profile_name,
        )

    @classmethod
    def profile_for(cls, building_type: Any, cfg: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
        """("office" | "hotel" | "school", profile config) for a building type; offices by default."""
        cfg = cfg or load_config()
        kind = normalize_type(building_type)
        profiles = cfg.get("profiles") or {}
        for name, profile in profiles.items():
            if kind in {normalize_type(t) for t in profile.get("building_types") or []}:
                return name, profile
        return "office", profiles.get("office", {})

    # ------------------------------------------------------------------ preparation
    @staticmethod
    def to_local_index(index: pd.Index, timezone: Optional[str] = None) -> pd.Index:
        """Timezone-aware index -> naive local wall-clock time (``timezone`` if given)."""
        if isinstance(index, pd.DatetimeIndex) and index.tz is not None:
            if timezone:
                index = index.tz_convert(timezone)
            return index.tz_localize(None)
        return index

    @classmethod
    def _prepare_series(
        cls,
        timeseries_data: Dict[str, pd.Series],
        metadata: Dict[str, Any],
        occupancy_filtered: bool,
    ) -> Dict[str, pd.Series]:
        """Local time; opening-hours filter unless the caller already applied one."""
        profile = None if occupancy_filtered else get_opening_profile_for_building_type(
            normalize_type(metadata.get("building_type")) or None
        )
        prepared: Dict[str, pd.Series] = {}
        for param, series in timeseries_data.items():
            if not isinstance(series, pd.Series) or series.empty:
                continue
            series = series.copy()
            series.index = cls.to_local_index(series.index, metadata.get("timezone"))
            if profile is not None and isinstance(series.index, pd.DatetimeIndex):
                mask = generate_occupancy_mask(series.index, profile)
                series = series[mask.to_numpy(dtype=bool)]
            prepared[param] = series.dropna()
        return prepared

    @classmethod
    def _normalize_parameter_name(cls, parameter: str) -> str:
        token = str(parameter).lower().replace(" ", "").replace("_", "")
        return cls.PARAMETER_ALIASES.get(token, str(parameter).lower())

    @classmethod
    def _get_parameter_evaluator(cls, parameter: str) -> Callable[..., Outcome]:
        evaluators = {
            "temperature": cls._evaluate_temperature,
            "relative_humidity": cls._evaluate_humidity,
            "co2": cls._evaluate_co2,
            "pm25": cls._evaluate_pm25,
            "formaldehyde": cls._evaluate_formaldehyde,
            "benzene": cls._evaluate_benzene,
            "radon": cls._evaluate_radon,
            "ventilation": cls._evaluate_ventilation,
            "mold": cls._evaluate_mold,
            "noise": cls._evaluate_noise,
            "illuminance": cls._evaluate_illuminance,
            "daylight_factor": cls._evaluate_daylight_factor,
            "no2": cls._evaluate_no2,
            "reverberation_time": cls._evaluate_reverberation_time,
        }
        return evaluators[parameter]

    @classmethod
    def _is_hotel(cls, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
        hotel_types = {normalize_type(t) for t in cfg.get("hotel_building_types") or []}
        return normalize_type(metadata.get("building_type")) in hotel_types

    @classmethod
    def _building_rule(cls, metadata: Dict[str, Any], cfg: Dict[str, Any], pcfg: Dict[str, Any]) -> str:
        """tail.R's BuildingType for RH and illuminance: 'hotel' or 'office' (also the default)."""
        return "hotel" if cls._is_hotel(metadata, cfg) else str(pcfg.get("default_building_type", "office"))

    # ------------------------------------------------------------------ thermal
    @classmethod
    def _evaluate_temperature(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        pcfg = cfg["parameters"]["temperature"]
        values = cls._numeric_series(series)
        if values.empty:
            return None
        values = r_round(values, int(pcfg["round"]))  # l.84
        if isinstance(values.index, pd.DatetimeIndex):
            # Season per sample by month (l.85-87): heating October-May, non-heating June-September.
            heating = np.asarray(values.index.month.isin(list(pcfg["heating_months"])))
            season_basis = "month of each sample"
        else:
            hint = cls._season_from_hint(metadata.get("season_hint"))
            if hint is None:
                return "No timestamps: the heating/non-heating season (by month) is unknown."
            heating = np.full(len(values), hint == "heating")
            season_basis = f"season hint '{hint}' (no timestamps)"
        bands = pcfg["bands"]
        non_heating_colors = cls._band_colors(values, bands["non_heating"])  # l.95-100
        adaptive = cls._adaptive_colors(values, metadata, cfg) if isinstance(values.index, pd.DatetimeIndex) else None
        adaptive_used = adaptive is not None and bool(((~heating) & (adaptive != "")).any())
        if adaptive is not None:
            # Buildings without mechanical cooling (TAIL paper Table 2): adaptive bands outside
            # the heating season wherever the running mean outdoor temperature is known.
            non_heating_colors = np.where(adaptive != "", adaptive, non_heating_colors)
        colors = np.where(
            heating,
            cls._band_colors(values, bands["heating"]),  # l.89-94
            non_heating_colors,
        )
        counts = cls._color_counts(colors)
        rating = cls._time_share_rating(counts, cfg["time_share_rule"])  # l.357-369
        return cls._build_parameter_result(
            parameter="temperature",
            category=TAILCategory.THERMAL,
            rating=rating,
            counts=counts,
            sample_count=int(values.size),
            summary_value=round(float(values.mean()), 2),
            metadata={
                "rule": "time shares (cumulative reading of tail.R l.357-369)",
                "season_basis": season_basis,
                "heating_samples": int(heating.sum()),
                "non_heating_samples": int((~heating).sum()),
                "bands": bands,
                "adaptive": adaptive_used,
            },
        )

    @classmethod
    def running_mean_outdoor(cls, daily: pd.Series, alpha: float = 0.8, days: int = 30) -> pd.Series:
        """theta_rm per day from daily mean outdoor temperatures: (1 - alpha) * sum(alpha^i * theta_ed-1-i)
        over the preceding days (normalised over the days available, up to ``days``)."""
        daily = daily.dropna().sort_index()
        values = daily.to_numpy(dtype=float)
        out = np.full(len(values), np.nan)
        for i in range(1, len(values)):
            prev = values[max(0, i - days):i][::-1]
            w = alpha ** np.arange(len(prev))
            out[i] = float((w * prev).sum() / w.sum())
        return pd.Series(out, index=daily.index)

    @classmethod
    def _adaptive_colors(cls, values: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Optional[np.ndarray]:
        """Per sample: Green/Yellow/Orange/Red from the adaptive bands, "" where they don't apply
        (no running mean, or above its validity range). None if the building has cooling or no
        outdoor temperature."""
        if metadata.get("mechanical_cooling") is not False:
            return None
        raw = metadata.get("outdoor_daily_mean_temperature")
        if isinstance(raw, dict) and raw:
            daily = pd.Series(list(raw.values()), index=pd.to_datetime(list(raw.keys())), dtype=float)
        elif isinstance(raw, pd.Series) and not raw.empty:
            daily = raw.resample("D").mean() if isinstance(raw.index, pd.DatetimeIndex) else raw
        else:
            return None
        acfg = cfg["adaptive_temperature"]
        rm_daily = cls.running_mean_outdoor(daily)
        rm = rm_daily.reindex(values.index.normalize()).to_numpy(dtype=float)
        lo_rm = np.clip(rm, *acfg["lower_valid"])
        hi_rm = np.clip(rm, *acfg["upper_valid"])
        v = values.to_numpy(dtype=float)
        colors = np.full(len(v), "red", dtype=object)
        for color in ("orange", "yellow", "green"):  # narrowest band last wins
            below, above = acfg["offsets"][color]
            inside = (v >= 0.33 * lo_rm + 18.8 + below) & (v <= 0.33 * hi_rm + 18.8 + above)
            colors[inside] = color
        colors[np.isnan(rm) | (rm > acfg["upper_valid"][1])] = ""
        return colors.astype(str)

    @classmethod
    def _evaluate_humidity(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        pcfg = cfg["parameters"]["relative_humidity"]
        values = cls._numeric_series(series)
        if values.empty:
            return None
        values = values.where(values >= pcfg["floor"], float(pcfg["floor"]))  # l.108-109
        values = values.where(values <= 100, float(pcfg["above_100"]))  # l.110
        values = r_round(values, int(pcfg["round"]))  # l.111
        rule = cls._building_rule(metadata, cfg, pcfg)
        bands = pcfg["bands"][rule]  # l.113-123
        counts = cls._color_counts(cls._band_colors(values, bands))
        rating = cls._time_share_rating(counts, cfg["time_share_rule"])  # l.457-470
        return cls._build_parameter_result(
            parameter="relative_humidity",
            category=TAILCategory.IAQ,
            rating=rating,
            counts=counts,
            sample_count=int(values.size),
            summary_value=round(float(values.mean()), 2),
            metadata={
                "rule": "time shares (cumulative reading of tail.R l.457-470)",
                "building_type_rule": rule,
                "building_type": metadata.get("building_type"),
                "bands": bands,
            },
        )

    # ------------------------------------------------------------------ indoor air
    @classmethod
    def _evaluate_co2(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        pcfg = cfg["parameters"]["co2"]
        values = cls._numeric_series(series)
        if values.empty:
            return None
        outdoor = metadata.get("outdoor_co2_ppm")
        outdoor = float(pcfg["outdoor_ppm"] if outdoor is None else outdoor)
        values = values.where(values >= outdoor, outdoor)  # l.153
        p95 = float(values.quantile(pcfg["percentile"] / 100.0))  # l.157 (R type 7 = pandas linear)
        limits = {c: outdoor + float(v) for c, v in pcfg["above_outdoor"].items()}  # 970/1220/1770 (l.163-166)
        counts = cls._color_counts(np.array([cls._color_at_most(v, limits) for v in values]))
        if pcfg.get("rule") == "time_share":
            # TAIL for schools (Tran 2024, Fig. 8): >= 94 % of the time within the category
            rating = cls._time_share_rating(counts, cfg["time_share_rule"])
            return cls._build_parameter_result(
                parameter="co2", category=TAILCategory.IAQ, rating=rating, counts=counts,
                sample_count=int(values.size), summary_value=round(p95, 2),
                metadata={"rule": "time shares (TAIL for schools, Fig. 8)", "outdoor_ppm": outdoor, "limits_ppm": limits},
            )
        color = cls._color_at_most(p95, limits)
        return cls._build_parameter_result(
            parameter="co2",
            category=TAILCategory.IAQ,
            rating=cls.COLOR_TO_RATING[color],
            counts=counts,
            sample_count=int(values.size),
            summary_value=round(p95, 2),
            metadata={
                "rule": f"P{pcfg['percentile']} of occupied values (tail.R l.156-168)",
                "percentile": pcfg["percentile"],
                "outdoor_ppm": outdoor,
                "limits_ppm": limits,
            },
        )

    @classmethod
    def _evaluate_pm25(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        return cls._evaluate_pollutant("pm25", series, cfg)  # l.131-144, 515-527

    @classmethod
    def _evaluate_formaldehyde(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        return cls._evaluate_pollutant("formaldehyde", series, cfg)  # l.175-189, 497-509

    @classmethod
    def _evaluate_benzene(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        return cls._evaluate_pollutant("benzene", series, cfg)  # l.192-205, 479-491

    @classmethod
    def _evaluate_radon(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        return cls._evaluate_pollutant("radon", series, cfg)  # l.208-221, 534-546

    @classmethod
    def _evaluate_pollutant(cls, parameter: str, series: pd.Series, cfg: Dict[str, Any]) -> Outcome:
        """Green/Yellow/Red pollutants: any Red -> IV, else any Yellow -> II, else I."""
        limits = cfg["parameters"][parameter]["limits"]
        values = cls._numeric_series(series)
        values = values[values >= 0]  # negative -> NA
        if values.empty:
            return None
        values = values.where(values >= 1, 0.0)  # values under 1 -> 0
        values = r_round(values, 0)
        v = values.to_numpy()
        colors = np.where(v < limits["green_below"], "green", np.where(v < limits["yellow_below"], "yellow", "red"))
        counts = cls._color_counts(colors)
        if counts["red"]:
            rating = TAILRating.POOR
        elif counts["yellow"]:
            rating = TAILRating.GOOD
        else:
            rating = TAILRating.EXCELLENT
        return cls._build_parameter_result(
            parameter=parameter,
            category=TAILCategory.IAQ,
            rating=rating,
            counts=counts,
            sample_count=int(values.size),
            summary_value=round(float(values.max()), 2),
            metadata={"rule": "any Red sample -> IV, any Yellow -> II, else I", "summary": "maximum", "limits": limits},
        )

    @classmethod
    def _evaluate_ventilation(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        pcfg = cfg["parameters"]["ventilation"]
        values = cls._numeric_series(series)
        if values.empty:
            return None
        persons = cls._first_number(metadata, ("design_occupancy", "design_occupants", "persons", "occupancy"))
        area = cls._first_number(metadata, ("area_m2", "floor_area_m2"))
        missing = [name for name, value in (("number of persons", persons), ("floor area", area)) if value is None]
        if missing:
            return ("Not rated: the TAIL ventilation limits (l/s per person plus l/s per m²) need the "
                    + " and ".join(missing) + " of the space.")
        values = r_round(values, int(pcfg["round"]))  # l.227
        values = values[values >= 0]  # l.228
        if values.empty:
            return None
        # l.58-60: required supply = per person * persons + per m² * floor area
        limits = {c: pcfg["per_person"][c] * persons + pcfg["per_m2"][c] * area for c in ("green", "yellow", "orange")}
        colors = np.array([cls._color_at_least(v, limits) for v in values])  # l.229-235
        counts = cls._color_counts(colors)
        return cls._build_parameter_result(
            parameter="ventilation",
            category=TAILCategory.IAQ,
            rating=cls._worst_rating(counts),  # l.408-422: worst category
            counts=counts,
            sample_count=int(values.size),
            summary_value=round(float(values.min()), 2),
            metadata={"rule": "worst sample", "summary": "minimum", "persons": persons, "area_m2": area,
                      "limits_l_s": {c: round(v, 2) for c, v in limits.items()}},
        )

    @classmethod
    def _evaluate_mold(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        pcfg = cfg["parameters"]["mold"]
        if not isinstance(series, pd.Series) or series.dropna().empty:
            return None

        def norm(text: Any) -> str:
            return re.sub(r"\s+", " ", str(text).strip().lower())

        lookup: Dict[str, str] = {}
        for source in ("keys", "phrases"):  # tail.R's phrases win over short keys
            for color, entries in (pcfg.get(source) or {}).items():
                for entry in entries:
                    lookup[norm(entry)] = color
        area_limits = pcfg["area_cm2"]
        colors: List[str] = []
        unrecognised: List[str] = []
        for entry in series.dropna():
            color: Optional[str]
            if isinstance(entry, (int, float, np.number)) and not isinstance(entry, bool):
                area = float(entry)  # visible mould area in cm²
                if area < 0:
                    color = None
                elif area == 0:
                    color = "green"
                elif area < area_limits["yellow_below"]:
                    color = "yellow"
                elif area < area_limits["orange_below"]:
                    color = "orange"
                else:
                    color = "red"
            else:
                color = lookup.get(norm(entry))  # l.245-248
            if color is None:
                unrecognised.append(str(entry))
            else:
                colors.append(color)
        if not colors:
            return "Not rated: no mould observation matches tail.R's inspection phrases."
        counts = cls._color_counts(np.array(colors))
        meta: Dict[str, Any] = {"rule": "worst observation (tail.R l.430-440)"}
        if unrecognised:
            meta["unrecognised"] = unrecognised[:10]
        return cls._build_parameter_result(
            parameter="mold",
            category=TAILCategory.IAQ,
            rating=cls._worst_rating(counts),
            counts=counts,
            sample_count=len(colors),
            summary_value=None,
            metadata=meta,
        )

    # ------------------------------------------------------------------ acoustic
    @classmethod
    def _noise_room_type(cls, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Optional[str]:
        room_types = cfg["parameters"]["noise"]["room_types"]
        room = normalize_type(metadata.get("room_type"))
        for key, aliases in room_types.items():
            if room == key or room in {normalize_type(a) for a in aliases}:
                return key
        if not room and cls._is_hotel(metadata, cfg):
            return "hotel"
        return None

    @classmethod
    def _evaluate_noise(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        pcfg = cfg["parameters"]["noise"]
        values = cls._numeric_series(series)
        if values.empty:
            return None
        room_type = cls._noise_room_type(metadata, cfg)
        if room_type is None:
            return (f"Not rated: TAIL sets noise limits for small offices, open offices and hotel rooms only "
                    f"(room type '{metadata.get('room_type') or 'unknown'}').")
        values = r_round(values, int(pcfg["round"]))  # l.260
        values = values.where(values >= pcfg["floor"], float(pcfg["floor"]))  # l.261
        p5 = float(values.quantile(pcfg["percentile"] / 100.0))  # l.265
        limits = {c: float(v) for c, v in pcfg["limits"][room_type].items()}
        color = cls._color_at_most(p5, limits)  # l.271-282
        counts = cls._color_counts(np.array([cls._color_at_most(v, limits) for v in values]))
        return cls._build_parameter_result(
            parameter="noise",
            category=TAILCategory.ACOUSTIC,
            rating=cls.COLOR_TO_RATING[color],
            counts=counts,
            sample_count=int(values.size),
            summary_value=round(p5, 2),
            metadata={"rule": f"P{pcfg['percentile']} (tail.R l.264-284)", "percentile": pcfg["percentile"],
                      "room_type": room_type, "limits_db": limits},
        )

    # ------------------------------------------------------------------ luminous
    @classmethod
    def _evaluate_illuminance(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        pcfg = cfg["parameters"]["illuminance"]
        values = cls._numeric_series(series)
        if values.empty:
            return None
        values = values.where(values >= pcfg["floor"], float(pcfg["floor"]))  # l.292
        if pcfg.get("rule") == "time_share_min_lux":
            # TAIL for schools (Table 9): total illuminance >= 500 / 300 / 200 lx. The thesis rates
            # spot measurements; for continuous logs hvx applies the >= 94 % time-share rule.
            lim = pcfg["min_lux"]
            v = values.to_numpy()
            colors = np.where(v >= lim["green"], "green", np.where(v >= lim["yellow"], "yellow",
                                                                    np.where(v >= lim["orange"], "orange", "red")))
            counts = cls._color_counts(colors)
            return cls._build_parameter_result(
                parameter="illuminance", category=TAILCategory.LUMINOUS,
                rating=cls._time_share_rating(counts, cfg["time_share_rule"]), counts=counts,
                sample_count=int(values.size), summary_value=round(float(values.median()), 0),
                metadata={"rule": "TAIL for schools, Table 9 (time shares)", "min_lux": lim},
            )
        rule = cls._building_rule(metadata, cfg, pcfg)
        rcfg = pcfg[rule]
        if rule == "hotel":
            # l.309-314: share of time at or above 100 lx
            share = float((values >= rcfg["at_least_lux"]).mean() * 100.0)
            if share <= rcfg["green_max_pct"]:
                color = "green"
            elif share <= rcfg["yellow_max_pct"]:
                color = "yellow"
            elif share <= rcfg["orange_max_pct"]:
                color = "orange"
            else:
                color = "red"
            basis = f"share of time >= {rcfg['at_least_lux']} lx"
        else:
            # l.301-306: share of time within 300-500 lx
            low, high = rcfg["within_lux"]
            share = float(((values >= low) & (values <= high)).mean() * 100.0)
            if share > rcfg["green_above_pct"]:
                color = "green"
            elif share >= rcfg["yellow_min_pct"]:
                color = "yellow"
            elif share >= rcfg["orange_min_pct"]:
                color = "orange"
            else:
                color = "red"
            basis = f"share of time within {low}-{high} lx"
        counts = {c: 0 for c in COLORS}
        counts[color] = 1
        return cls._build_parameter_result(
            parameter="illuminance",
            category=TAILCategory.LUMINOUS,
            rating=cls.COLOR_TO_RATING[color],
            counts=counts,
            sample_count=int(values.size),
            summary_value=round(share, 2),
            metadata={"rule": basis, "building_type_rule": rule, "share_pct": round(share, 2), "limits": rcfg},
            compliance=share if rule != "hotel" else None,
        )

    @classmethod
    def _evaluate_daylight_factor(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        limits = cfg["parameters"]["daylight_factor"]["min"]
        values = cls._numeric_series(series)
        if values.empty:
            return None
        counts = cls._color_counts(np.array([cls._color_at_least(v, limits) for v in values]))  # l.328-333
        return cls._build_parameter_result(
            parameter="daylight_factor",
            category=TAILCategory.LUMINOUS,
            rating=cls._worst_rating(counts),  # l.620-631
            counts=counts,
            sample_count=int(values.size),
            summary_value=round(float(values.min()), 2),
            metadata={"rule": "worst value", "summary": "minimum", "limits_pct": limits},
        )

    # ------------------------------------------------------------------ hvx extensions
    @classmethod
    def _evaluate_no2(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        return cls._evaluate_pollutant("no2", series, cfg)  # TAIL for schools, Table 8

    @classmethod
    def _evaluate_reverberation_time(cls, series: pd.Series, metadata: Dict[str, Any], cfg: Dict[str, Any]) -> Outcome:
        """TAIL for schools, Table 7: by classroom volume; III has no criteria, so II -> IV."""
        pcfg = cfg["parameters"]["reverberation_time"]
        values = cls._numeric_series(series)
        if values.empty:
            return None
        volume = cls._first_number(metadata, ("volume_m3", "room_volume_m3"))
        if volume is None:
            return "Not rated: reverberation time limits depend on the classroom volume (volume_m3)."
        rt = float(values.median())
        bands = pcfg["small"] if volume < float(pcfg["small_room_volume_m3"]) else pcfg["large"]
        if bands["green"][0] <= rt <= bands["green"][1]:
            color = "green"
        elif bands["yellow"][0] <= rt <= bands["yellow"][1]:
            color = "yellow"
        else:
            color = "red"
        counts = {c: 0 for c in COLORS}
        counts[color] = 1
        return cls._build_parameter_result(
            parameter="reverberation_time", category=TAILCategory.ACOUSTIC, rating=cls.COLOR_TO_RATING[color],
            counts=counts, sample_count=int(values.size), summary_value=round(rt, 2),
            metadata={"rule": "TAIL for schools, Table 7", "volume_m3": volume, "bands_s": bands},
        )

    @classmethod
    def _evaluate_extension(cls, parameter: str, series: pd.Series, cfg: Dict[str, Any]) -> Outcome:
        pcfg = (cfg.get("extensions") or {}).get(parameter)
        values = cls._numeric_series(series)
        if not pcfg or values.empty:
            return None
        counts = cls._color_counts(cls._band_colors(values, pcfg["bands"]))
        return cls._build_parameter_result(
            parameter=parameter,
            category=cls.EXTENSION_CATEGORIES[parameter],
            rating=cls._worst_rating(counts),
            counts=counts,
            sample_count=int(values.size),
            summary_value=round(float(values.mean()), 2),
            metadata={"rule": "worst sample (hvx limits)", "note": "hvx extension, not a TAIL parameter",
                      "bands": pcfg["bands"]},
            extension=True,
        )

    # ------------------------------------------------------------------ aggregation
    @classmethod
    def _build_category_results(
        cls, parameter_results: List[TAILParameterResult]
    ) -> Dict[TAILCategory, TAILCategoryResult]:
        grouped: Dict[TAILCategory, List[TAILParameterResult]] = {cat: [] for cat in TAILCategory}
        for result in parameter_results:
            if not result.extension:
                grouped[result.category].append(result)

        category_results: Dict[TAILCategory, TAILCategoryResult] = {}
        for category, params in grouped.items():
            if not params:
                continue
            worst_rating = max(param.rating for param in params)  # worst parameter (l.554, 640)
            compliance = sum(param.metadata.get("compliance_rate", 0.0) for param in params) / len(params)
            category_results[category] = TAILCategoryResult(
                category=category,
                rating=worst_rating,
                rating_label=worst_rating.to_label(),
                compliance_rate=round(compliance, 2),
                parameter_count=len(params),
                parameters=params,
                dominant_color=worst_rating.to_color(),
            )
        return category_results

    @classmethod
    def _summarize_overall(
        cls, category_results: Dict[TAILCategory, TAILCategoryResult]
    ) -> Tuple[Optional[TAILRating], float]:
        if not category_results:
            return None, 0.0
        worst_rating = max(category.rating for category in category_results.values())  # l.652
        compliance = sum(cat.compliance_rate for cat in category_results.values()) / len(category_results)
        return worst_rating, compliance

    @classmethod
    def _parameter_payload(cls, param: TAILParameterResult) -> Dict[str, Any]:
        return {
            "rating": param.rating_label,
            "rating_color": param.rating.to_color(),
            "dominant_color": param.dominant_color,
            "distribution": param.distribution,
            "samples": param.sample_count,
            "summary_value": param.summary_value,
            "metadata": param.metadata,
        }

    @classmethod
    def _build_visualization(
        cls,
        parameter_results: List[TAILParameterResult],
        category_results: Dict[TAILCategory, TAILCategoryResult],
        overall_rating: Optional[TAILRating],
        overall_compliance: float,
        metadata: Dict[str, Any],
        building_name: Optional[str],
        extensions: Optional[List[TAILParameterResult]] = None,
        not_rated: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        visualization: Dict[str, Any] = {
            "entity": building_name or metadata.get("entity_name"),
            "overall": {
                "rating": overall_rating.to_label() if overall_rating else None,
                "rating_color": overall_rating.to_color() if overall_rating else None,
                "compliance": round(overall_compliance, 2),
            },
            "domains": {},
            "extensions": {p.parameter: cls._parameter_payload(p) for p in extensions or []},
            "not_rated": dict(not_rated or {}),
            "metadata": {
                "building_type": metadata.get("building_type"),
                "room_type": metadata.get("room_type"),
                "area_m2": metadata.get("area_m2"),
                "design_occupancy": metadata.get("design_occupancy"),
            },
        }
        for category, result in category_results.items():
            visualization["domains"][category.value] = {
                "rating": result.rating_label,
                "rating_color": result.rating.to_color(),
                "compliance": result.compliance_rate,
                "dominant_color": result.dominant_color,
                "parameters": {p.parameter: cls._parameter_payload(p) for p in result.parameters},
            }
        return visualization

    # ------------------------------------------------------------------ rules and helpers
    @classmethod
    def _numeric_series(cls, series: pd.Series) -> pd.Series:
        if not isinstance(series, pd.Series):
            return pd.Series(dtype=float)
        return pd.to_numeric(series, errors="coerce").dropna().astype(float)

    @staticmethod
    def _first_number(metadata: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[float]:
        for key in keys:
            value = metadata.get(key)
            if value is None or isinstance(value, bool):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if np.isfinite(number) and number >= 0:
                return number
        return None

    @staticmethod
    def _season_from_hint(hint: Optional[str]) -> Optional[str]:
        token = normalize_type(hint)
        if token in ("heating", "winter", "autumn"):
            return "heating"
        if token in ("non_heating", "nonheating", "cooling", "summer"):
            return "non_heating"
        return None

    @staticmethod
    def _band_colors(values: pd.Series, bands: Mapping[str, Any]) -> np.ndarray:
        """Nested closed intervals: first of green/yellow/orange containing the value, else red."""
        v = np.asarray(values, dtype=float)
        colors = np.full(v.shape, "red", dtype=object)
        for color in ("orange", "yellow", "green"):  # inner bands overwrite outer ones
            low, high = bands[color]
            inside = np.ones(v.shape, dtype=bool)
            if low is not None:
                inside &= v >= low
            if high is not None:
                inside &= v <= high
            colors[inside] = color
        return colors

    @staticmethod
    def _color_at_most(value: float, limits: Mapping[str, float]) -> str:
        """Green if value <= green limit, Yellow if <= yellow, Orange if <= orange, else Red."""
        for color in ("green", "yellow", "orange"):
            if value <= limits[color]:
                return color
        return "red"

    @staticmethod
    def _color_at_least(value: float, limits: Mapping[str, float]) -> str:
        """Green if value >= green limit, Yellow if >= yellow, Orange if >= orange, else Red."""
        for color in ("green", "yellow", "orange"):
            if value >= limits[color]:
                return color
        return "red"

    @staticmethod
    def _color_counts(colors: np.ndarray) -> Dict[str, int]:
        colors = np.asarray(colors)
        return {c: int((colors == c).sum()) for c in COLORS}

    @classmethod
    def _worst_rating(cls, counts: Dict[str, int]) -> TAILRating:
        for color in reversed(COLORS):
            if counts.get(color, 0) > 0:
                return cls.COLOR_TO_RATING[color]
        return TAILRating.EXCELLENT

    @staticmethod
    def _time_share_rating(counts: Dict[str, int], rule: Mapping[str, Mapping[str, float]]) -> TAILRating:
        """
        Time-share label, tail.R l.357-369 read cumulatively: the first of I, II,
        III whose conditions hold, otherwise IV. tail.R also requires Yellow > 5 %
        for II and Orange > 5 % for III; dropping those lower bounds only closes
        the gaps where tail.R falls through to IV (e.g. 99.5 % Green + 0.5 % Red).
        """
        total = sum(counts.values())
        if not total:
            return TAILRating.POOR
        share = {c: counts.get(c, 0) / total for c in COLORS}
        for label in ("I", "II", "III"):
            cond = rule[label]
            if (
                share["green"] >= cond.get("green_min", 0.0)
                and share["orange"] <= cond.get("orange_max", 1.0)
                and share["red"] <= cond.get("red_max", 1.0)
            ):
                return TAILRating.from_label(label)
        return TAILRating.POOR

    @classmethod
    def _build_parameter_result(
        cls,
        parameter: str,
        category: TAILCategory,
        rating: TAILRating,
        counts: Dict[str, int],
        sample_count: int,
        summary_value: Optional[float],
        metadata: Dict[str, Any],
        extension: bool = False,
        compliance: Optional[float] = None,
    ) -> TAILParameterResult:
        distribution = cls._distribution(counts)
        metadata = dict(metadata)
        # hvx's informative "compliance": share Green plus half the share Yellow (not part of TAIL)
        metadata["compliance_rate"] = round(compliance, 2) if compliance is not None else round(
            distribution["green"] + 0.5 * distribution["yellow"], 2
        )
        return TAILParameterResult(
            parameter=parameter,
            category=category,
            rating=rating,
            rating_label=rating.to_label(),
            dominant_color=rating.to_color(),
            distribution=distribution,
            sample_count=sample_count,
            summary_value=summary_value,
            metadata=metadata,
            extension=extension,
        )

    @classmethod
    def _distribution(cls, counts: Dict[str, int]) -> Dict[str, float]:
        total = sum(counts.values())
        if total == 0:
            return {color: 0.0 for color in COLORS}
        return {color: round(counts.get(color, 0) / total * 100.0, 2) for color in COLORS}


__all__ = [
    "TAILCalculator",
    "TAILCategory",
    "TAILCategoryResult",
    "TAILOverallResult",
    "TAILParameterResult",
    "TAILRating",
    "load_config",
    "normalize_type",
    "r_round",
]

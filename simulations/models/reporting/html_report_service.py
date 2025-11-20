from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
from jinja2 import Template

from core.entities import Building, Floor, Portfolio, Room
from core.data_quality import DataQualityAnalyzer, analyze_dataframe_quality
from simulations.models.correlations import ClimateCorrelationModel, ClimateCorrelationResult
from simulations.models.recommendations import (
    SmartRecommendation,
    SmartRecommendationsModel,
)
from simulations.models.scenario import ScenarioImpactModel, ScenarioImpactSummary
from simulations.models.ventilation import VentilationCalculator, VentilationRateResult


@dataclass
class RoomReportRow:
    """Container used by the template layer."""

    room_id: str
    room_name: str
    building_id: str
    building_name: str
    achieved_category: Optional[str]
    best_compliance_rate: Optional[float]
    compliance: Dict[str, Optional[float]]
    correlations: ClimateCorrelationResult
    ventilation: Optional[VentilationRateResult]
    scenario_impacts: ScenarioImpactSummary
    recommendations: List[SmartRecommendation] = field(default_factory=list)
    data_quality: Optional[Dict[str, Any]] = None

    def as_dict(self) -> dict:
        return {
            "room_id": self.room_id,
            "room_name": self.room_name,
            "building_id": self.building_id,
            "building_name": self.building_name,
            "achieved_category": self.achieved_category,
            "best_compliance_rate": self.best_compliance_rate,
            "compliance": self.compliance,
            "correlations": self.correlations.as_dict(),
            "ventilation": self._format_ventilation(),
            "scenarios": self._scenario_entries(),
            "recommendations": [rec.as_dict() for rec in self.recommendations],
            "data_quality": self.data_quality or {},
        }

    def _format_ventilation(self) -> Optional[dict]:
        if not self.ventilation:
            return None
        return {
            "ach": self.ventilation.ach,
            "category": self.ventilation.category,
            "quality": self.ventilation.quality_score,
            "r_squared": self.ventilation.r_squared,
            "description": self.ventilation.description,
        }

    def _scenario_entries(self) -> List[dict]:
        summary = self.scenario_impacts.as_dict()
        entries: List[dict] = []
        for key in ("ventilation", "solar_shading"):
            scenario = summary.get(key)
            if scenario:
                entries.append(scenario)
        return entries


class HTMLReportService:
    """
    Generate an HTML report aimed at facility managers, combining EN 16798 scores,
    simulation outputs, correlations and scenario impacts.
    """

    def __init__(
        self,
        season: str = "winter",
        temperature_band: Tuple[float, float] = (20.0, 24.0),
        co2_threshold: float = 1200.0,
        analyze_full_year: bool = False,
    ) -> None:
        self.season = season
        self.analyze_full_year = analyze_full_year
        self.seasons = self._determine_seasons(season, analyze_full_year)
        self.temperature_band = temperature_band
        self.co2_threshold = co2_threshold

        self.ventilation_calc = VentilationCalculator()
        self.correlation_model = ClimateCorrelationModel(
            temperature_band=temperature_band,
            co2_threshold=co2_threshold,
        )
        self.scenario_model = ScenarioImpactModel(
            temp_band=temperature_band,
            co2_threshold=co2_threshold,
        )
        self.recommendation_model = SmartRecommendationsModel()
        self.metric_aliases = {
            "temperatur": "temperature",
            "temperature": "temperature",
            "temp": "temperature",
            "fugtighed": "humidity",
            "relativ fugt": "humidity",
            "co2": "co2",
            "co₂": "co2",
            "lys": "illuminance",
            "tilstedeværelse": "occupancy",
            "occupancy": "occupancy",
            "outdoor temperature": "outdoor_temperature",
            "udendørs temperatur": "outdoor_temperature",
            "outdoor humidity": "outdoor_humidity",
            "udendørs fugt": "outdoor_humidity",
            "solar_irradiance": "solar_radiation",
            "solar irradiance": "solar_radiation",
            "solstråling": "solar_radiation",
            "global_stråling": "solar_radiation",
        }
        self.data_quality_analyzer = DataQualityAnalyzer()
    
    def _determine_seasons(self, season: str, analyze_full_year: bool) -> List[str]:
        """Determine which seasons to analyze."""
        if analyze_full_year:
            return ["winter", "summer"]
        return [season]

    def generate_report(
        self,
        portfolio: Portfolio,
        buildings: Dict[str, Building],
        floors: Dict[str, Floor],
        rooms: Dict[str, Room],
        output_path: Path,
        entity_lookup: Optional[Callable[[str], Optional[Portfolio]]] = None,
    ) -> Path:
        """
        Build an HTML report and write it to `output_path`.
        """
        entity_lookup = entity_lookup or self._build_entity_lookup(portfolio, buildings, floors, rooms)

        room_rows = self._collect_room_rows(buildings, rooms, entity_lookup)
        building_results = self._collect_building_metrics(buildings, floors, rooms)
        building_rows = self._build_building_rows(buildings, rooms, building_results, room_rows)
        summary = self._build_summary(portfolio, buildings, rooms, room_rows)
        charts = self._build_charts(room_rows, building_rows)
        worst_rooms = self._find_worst_rooms(room_rows, buildings)

        html = self._render_template(
            portfolio=portfolio,
            summary=summary,
            building_rows=building_rows,
            room_rows=[row.as_dict() for row in room_rows],
            building_results=building_results,
            charts=charts,
            worst_rooms=worst_rooms,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        return output_path

    @staticmethod
    def _build_entity_lookup(
        portfolio: Portfolio,
        buildings: Dict[str, Building],
        floors: Dict[str, Floor],
        rooms: Dict[str, Room],
    ) -> Callable[[str], Optional[Room]]:
        registry: Dict[str, object] = {portfolio.id: portfolio}
        registry.update(buildings)
        registry.update(floors)
        registry.update(rooms)

        def lookup(entity_id: str) -> Optional[object]:
            return registry.get(entity_id)

        return lookup

    def _collect_building_metrics(
        self,
        buildings: Dict[str, Building],
        floors: Dict[str, Floor],
        rooms: Dict[str, Room],
    ) -> Dict[str, Dict[str, object]]:
        results: Dict[str, Dict[str, object]] = {}
        for building_id, building in buildings.items():
            cached = building.computed_metrics.get("standards_results")
            if cached:
                results[building_id] = cached
                continue

            metrics = building.compute_standards(
                floor_lookup=floors.get,
                room_lookup=rooms.get,
                season=self.season,
                force_recompute=False,
            )
            results[building_id] = metrics
        return results

    def _collect_room_rows(
        self,
        buildings: Dict[str, Building],
        rooms: Dict[str, Room],
        entity_lookup: Callable[[str], Optional[object]],
    ) -> List[RoomReportRow]:
        rows: List[RoomReportRow] = []
        for room_id, room in rooms.items():
            self._normalize_room_timeseries(room)
            if not room.has_data or not room.timestamps:
                continue

            building = buildings.get(room.building_id)
            df = self._room_dataframe(room, building)
            if df is None or df.empty:
                continue

            # Data quality analysis
            quality_metrics = analyze_dataframe_quality(df)
            quality_summary = {
                param: metrics.to_dict() 
                for param, metrics in quality_metrics.items()
            }

            compliance = self._compute_compliance(df)
            correlations = self.correlation_model.compute(df)
            ventilation_result = self._estimate_ventilation(df)
            scenario_impacts = self.scenario_model.estimate_impacts(df, ventilation_result)

            # Compute metrics for all seasons if full year analysis
            self._ensure_room_metrics_all_seasons(room, building, entity_lookup)
            
            # Get aggregated results across seasons
            summary = self._aggregate_season_results(room)

            recommendations = self.recommendation_model.generate(
                room.name,
                compliance,
                correlations,
                ventilation_result,
                scenario_impacts,
            )

            rows.append(
                RoomReportRow(
                    room_id=room_id,
                    room_name=room.name,
                    building_id=room.building_id or "n/a",
                    building_name=(building.name if building else room.building_id) or "n/a",
                    achieved_category=summary.get("achieved_category"),
                    best_compliance_rate=summary.get("best_compliance_rate"),
                    compliance=compliance,
                    correlations=correlations,
                    ventilation=ventilation_result,
                    scenario_impacts=scenario_impacts,
                    recommendations=recommendations,
                    data_quality=quality_summary,
                )
            )
        rows.sort(key=lambda r: (r.building_name, r.room_name))
        return rows

    def _ensure_room_metrics_all_seasons(
        self,
        room: Room,
        building: Optional[Building],
        entity_lookup: Callable[[str], Optional[object]],
    ) -> None:
        """Compute metrics for all seasons if full year analysis is enabled."""
        country = getattr(building, "country", None) or "DK"
        region = getattr(building, "region", None)
        building_type = getattr(building, "building_type", None) or "office"
        
        for season in self.seasons:
            # Store results per season
            season_key = f"standards_results_{season}"
            if season_key not in room.computed_metrics:
                room.compute_standards(
                    country=country,
                    region=region,
                    building_type=building_type,
                    season=season,
                    force_recompute=False,
                    entity_lookup=entity_lookup,
                )
                # Store with season suffix
                if "standards_results" in room.computed_metrics:
                    room.computed_metrics[season_key] = room.computed_metrics["standards_results"]
        
        if "simulation_results" not in room.computed_metrics:
            room.compute_simulations(force_recompute=False)
    
    def _aggregate_season_results(self, room: Room) -> Dict[str, Any]:
        """Aggregate EN16798 results across all analyzed seasons."""
        if not self.analyze_full_year:
            # Single season - return as-is
            return room.computed_metrics.get("standards_results", {}).get("en16798_1", {})
        
        # Aggregate across seasons
        season_results = []
        category_counts = {}
        
        for season in self.seasons:
            season_key = f"standards_results_{season}"
            if season_key in room.computed_metrics:
                en_result = room.computed_metrics[season_key].get("en16798_1", {})
                if en_result:
                    season_results.append(en_result)
                    
                    # Track category achievements
                    cat = en_result.get("achieved_category")
                    if cat:
                        category_counts[cat] = category_counts.get(cat, 0) + 1
        
        if not season_results:
            return {}
        
        # Determine overall achieved category (most restrictive that passes both seasons)
        # Category hierarchy: I (best) > II > III > IV (worst)
        category_order = ["I", "II", "III", "IV"]
        overall_category = None
        
        for cat in category_order:
            if category_counts.get(cat, 0) == len(self.seasons):
                overall_category = cat
                break
        
        # Average compliance rate
        avg_compliance = sum(r.get("best_compliance_rate", 0) for r in season_results) / len(season_results)
        
        # Aggregate time in category percentages
        avg_time_cat_I = sum(r.get("time_in_category_I_pct", 0) for r in season_results) / len(season_results)
        avg_time_cat_II = sum(r.get("time_in_category_II_pct", 0) for r in season_results) / len(season_results)
        avg_time_cat_III = sum(r.get("time_in_category_III_pct", 0) for r in season_results) / len(season_results)
        avg_time_cat_IV = sum(r.get("time_in_category_IV_pct", 0) for r in season_results) / len(season_results)
        
        return {
            "achieved_category": overall_category,
            "best_compliance_rate": round(avg_compliance, 2),
            "time_in_category_I_pct": round(avg_time_cat_I, 2),
            "time_in_category_II_pct": round(avg_time_cat_II, 2),
            "time_in_category_III_pct": round(avg_time_cat_III, 2),
            "time_in_category_IV_pct": round(avg_time_cat_IV, 2),
            "seasons_analyzed": self.seasons,
            "full_year": True,
        }

    def _room_dataframe(
        self,
        room: Room,
        building: Optional[Building],
    ) -> Optional[pd.DataFrame]:
        if not room.timeseries_data:
            return None

        columns = {}
        for metric, values in room.timeseries_data.items():
            columns[metric] = pd.Series(values)

        df = pd.concat(columns, axis=1)
        df = self._normalize_columns(df)

        if room.timestamps:
            idx = pd.to_datetime(room.timestamps, errors="coerce")
            valid_len = min(len(df), len(idx))
            df = df.iloc[:valid_len]
            df.index = idx[:valid_len]
        else:
            df.index = pd.RangeIndex(len(df))

        if "timestamp" in df.columns:
            df = df.drop(columns=["timestamp"])

        df = df.dropna(how="all")

        climate_df = self._climate_dataframe(building)
        if climate_df is not None:
            df = df.join(climate_df, how="left")
        return df

    def _climate_dataframe(self, building: Optional[Building]) -> Optional[pd.DataFrame]:
        if not building:
            return None

        frames = []
        climate_meta = building.metadata.get("climate_timeseries", {}) if building.metadata else {}
        for parameter, payload in climate_meta.items():
            timestamps = pd.to_datetime(payload.get("timestamps"))
            values = payload.get("values", [])
            frame = pd.DataFrame({parameter: values}, index=timestamps)
            frames.append(frame)

        if not frames:
            return None
        climate_df = pd.concat(frames, axis=1)
        return self._normalize_columns(climate_df)

    def _compute_compliance(self, df: pd.DataFrame) -> Dict[str, Optional[float]]:
        compliance: Dict[str, Optional[float]] = {}
        if "temperature" in df:
            lower, upper = self.temperature_band
            mask = (df["temperature"] < lower) | (df["temperature"] > upper)
            compliance["temperature"] = float((~mask).mean() * 100.0)
        else:
            compliance["temperature"] = None

        if "co2" in df:
            mask = df["co2"] > self.co2_threshold
            compliance["co2"] = float((~mask).mean() * 100.0)
        else:
            compliance["co2"] = None

        if "humidity" in df:
            mask = (df["humidity"] < 25.0) | (df["humidity"] > 60.0)
            compliance["humidity"] = float((~mask).mean() * 100.0)
        else:
            compliance["humidity"] = None

        return compliance

    def _estimate_ventilation(self, df: pd.DataFrame) -> Optional[VentilationRateResult]:
        if "co2" not in df:
            return None
        return self.ventilation_calc.estimate_from_co2_decay(df["co2"])

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        rename_map = {}
        for column in df.columns:
            normalized = self.metric_aliases.get(str(column).lower().strip())
            if normalized:
                rename_map[column] = normalized
        df = df.rename(columns=rename_map)
        if df.columns.duplicated().any():
            df = df.loc[:, ~df.columns.duplicated()]
        for column in df.columns:
            series = df[column]
            if series.dtype == object:
                df[column] = pd.to_numeric(series, errors="ignore")
        return df

    def _normalize_room_timeseries(self, room: Room) -> None:
        updated = dict(room.timeseries_data)
        lengths = []
        for key, values in list(updated.items()):
            normalized = self.metric_aliases.get(key.lower().strip())
            if normalized and normalized not in updated:
                updated[normalized] = values
            if isinstance(values, list):
                lengths.append(len(values))
        if lengths:
            min_len = min(lengths)
            for key, values in list(updated.items()):
                if isinstance(values, list) and len(values) > min_len:
                    updated[key] = values[:min_len]
            if room.timestamps:
                room.timestamps = room.timestamps[:min_len]
        room.timeseries_data = updated

    def _build_summary(
        self,
        portfolio: Portfolio,
        buildings: Dict[str, Building],
        rooms: Dict[str, Room],
        room_rows: List[RoomReportRow],
    ) -> Dict[str, object]:
        total_rooms = len(rooms)
        monitored_rooms = len(room_rows)
        monitoring_rate = (monitored_rooms / total_rooms * 100) if total_rooms else 0.0
        categories = [
            row.achieved_category for row in room_rows if row.achieved_category
        ]
        
        # Calculate category distribution
        category_counts = {"I": 0, "II": 0, "III": 0, "IV": 0}
        for cat in categories:
            if cat in category_counts:
                category_counts[cat] += 1
        
        total_categorized = sum(category_counts.values())
        category_percentages = {
            cat: round((count / total_categorized * 100), 1) if total_categorized > 0 else 0
            for cat, count in category_counts.items()
        }
        
        # Determine portfolio average category (conservative: 70% threshold)
        portfolio_category = self._determine_portfolio_category(category_counts, total_categorized)
        
        season_display = "Full Year (Winter + Summer)" if self.analyze_full_year else self.season.capitalize()

        return {
            "portfolio_name": portfolio.name,
            "season": season_display,
            "building_count": len(buildings),
            "room_count": total_rooms,
            "monitored_rooms": monitored_rooms,
            "monitoring_rate": round(monitoring_rate, 1),
            "achieved_categories": categories,
            "category_counts": category_counts,
            "category_percentages": category_percentages,
            "portfolio_category": portfolio_category,
        }
    
    def _determine_portfolio_category(self, category_counts: Dict[str, int], total: int) -> Optional[str]:
        """Determine portfolio category with 70% threshold."""
        if total == 0:
            return None
        
        category_order = ["I", "II", "III", "IV"]
        cumulative = 0
        
        for cat in category_order:
            cumulative += category_counts.get(cat, 0)
            if (cumulative / total) >= 0.70:
                return cat
        
        return None

    def _build_building_rows(
        self,
        buildings: Dict[str, Building],
        rooms: Dict[str, Room],
        building_results: Dict[str, Dict[str, object]],
        room_rows: List[RoomReportRow],
    ) -> List[dict]:
        grouped: Dict[str, List[RoomReportRow]] = {}
        for row in room_rows:
            grouped.setdefault(row.building_id, []).append(row)

        building_rows: List[dict] = []
        for building_id, building in buildings.items():
            monitored_rows = grouped.get(building_id, [])
            total_rooms = sum(1 for room in rooms.values() if room.building_id == building_id)
            avg_temp = self._average([row.compliance.get("temperature") for row in monitored_rows])
            avg_co2 = self._average([row.compliance.get("co2") for row in monitored_rows])

            # Aggregate building category from rooms
            room_categories = [row.achieved_category for row in monitored_rows if row.achieved_category]
            building_category = self._determine_building_category(room_categories)
            
            # Calculate category distribution for building
            cat_counts = {"I": 0, "II": 0, "III": 0, "IV": 0}
            for cat in room_categories:
                if cat in cat_counts:
                    cat_counts[cat] += 1
            
            total_cat = sum(cat_counts.values())
            cat_percentages = {
                cat: round((count / total_cat * 100), 1) if total_cat > 0 else 0
                for cat, count in cat_counts.items()
            }
            
            # Get time in category percentages from room rows
            time_cat_I = self._average([row.best_compliance_rate for row in monitored_rows 
                                       if row.achieved_category == "I"])
            time_cat_II = self._average([row.best_compliance_rate for row in monitored_rows 
                                        if row.achieved_category == "II"])
            time_cat_III = self._average([row.best_compliance_rate for row in monitored_rows 
                                         if row.achieved_category == "III"])
            time_cat_IV = self._average([row.best_compliance_rate for row in monitored_rows 
                                        if row.achieved_category == "IV"])
            
            en_summary = building_results.get(building_id, {}).get("en16798_1", {})
            key_recs = self._select_key_recommendations(
                [rec for row in monitored_rows for rec in row.recommendations]
            )

            building_rows.append(
                {
                    "building_id": building_id,
                    "building_name": building.name or building_id,
                    "achieved_category": building_category,
                    "category_counts": cat_counts,
                    "category_percentages": cat_percentages,
                    "time_in_category_I_pct": time_cat_I,
                    "time_in_category_II_pct": time_cat_II,
                    "time_in_category_III_pct": time_cat_III,
                    "time_in_category_IV_pct": time_cat_IV,
                    "rooms_total": total_rooms,
                    "rooms_monitored": len(monitored_rows),
                    "avg_temp_compliance": avg_temp,
                    "avg_co2_compliance": avg_co2,
                    "key_recommendations": [rec.as_dict() for rec in key_recs],
                }
            )

        building_rows.sort(key=lambda row: row["building_name"])
        return building_rows
    
    def _determine_building_category(self, room_categories: List[str]) -> Optional[str]:
        """Determine building category from room categories (70% threshold)."""
        if not room_categories:
            return None
        
        cat_counts = {"I": 0, "II": 0, "III": 0, "IV": 0}
        for cat in room_categories:
            if cat in cat_counts:
                cat_counts[cat] += 1
        
        total = sum(cat_counts.values())
        return self._determine_portfolio_category(cat_counts, total)

    @staticmethod
    def _average(values: List[Optional[float]]) -> Optional[float]:
        clean = [v for v in values if v is not None]
        if not clean:
            return None
        return round(sum(clean) / len(clean), 1)

    @staticmethod
    def _select_key_recommendations(
        recommendations: List[SmartRecommendation],
        limit: int = 3,
    ) -> List[SmartRecommendation]:
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_recs = sorted(
            recommendations,
            key=lambda rec: priority_order.get(rec.priority.lower(), 3),
        )
        unique: List[SmartRecommendation] = []
        seen_titles = set()
        for rec in sorted_recs:
            if rec.title in seen_titles:
                continue
            seen_titles.add(rec.title)
            unique.append(rec)
            if len(unique) >= limit:
                break
        return unique

    def _build_charts(
        self,
        room_rows: List[RoomReportRow],
        building_rows: List[dict],
    ) -> Dict[str, str]:
        charts: Dict[str, str] = {}

        room_temp = [
            (row.room_name, row.compliance.get("temperature"))
            for row in room_rows
            if row.compliance.get("temperature") is not None
        ]
        if room_temp:
            fig = go.Figure()
            fig.add_bar(x=[item[0] for item in room_temp], y=[item[1] for item in room_temp], marker_color="#2563eb")
            fig.update_layout(
                title="Room temperature compliance",
                xaxis_title="Room",
                yaxis_title="Compliance (%)",
                template="plotly_white",
            )
            charts["room_temperature"] = fig.to_html(full_html=False, include_plotlyjs="cdn")

        building_temp = [
            (row["building_name"], row["avg_temp_compliance"])
            for row in building_rows
            if row["avg_temp_compliance"] is not None
        ]
        if building_temp:
            fig = go.Figure()
            fig.add_bar(x=[item[0] for item in building_temp], y=[item[1] for item in building_temp], marker_color="#059669")
            fig.update_layout(
                title="Average building temperature compliance",
                xaxis_title="Building",
                yaxis_title="Compliance (%)",
                template="plotly_white",
            )
            charts["building_temperature"] = fig.to_html(full_html=False, include_plotlyjs="cdn")

        return charts

    def _find_worst_rooms(
        self,
        rows: List[RoomReportRow],
        buildings: Dict[str, Building],
    ) -> List[dict]:
        worst_by_building: Dict[str, RoomReportRow] = {}
        for row in rows:
            score = row.compliance.get("temperature") or 0.0
            current = worst_by_building.get(row.building_id)
            if not current or score < (current.compliance.get("temperature") or 0.0):
                worst_by_building[row.building_id] = row

        worst_rooms = []
        for building_id, row in worst_by_building.items():
            building = buildings.get(building_id)
            worst_rooms.append(
                {
                    "building_id": building_id,
                    "building_name": building.name if building else building_id,
                    "room_name": row.room_name,
                    "temperature_compliance": row.compliance.get("temperature"),
                    "co2_compliance": row.compliance.get("co2"),
                    "achieved_category": row.achieved_category,
                }
            )
        return worst_rooms

    def _render_template(
        self,
        portfolio: Portfolio,
        summary: Dict[str, object],
        building_rows: List[dict],
        room_rows: List[dict],
        building_results: Dict[str, Dict[str, object]],
        charts: Dict[str, str],
        worst_rooms: List[dict],
    ) -> str:
        template = Template(
            """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{{ summary.portfolio_name }} – IEQ report</title>
    <style>
      body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 32px; color: #0f172a; background: #f8fafc; }
      h1, h2, h3 { color: #0f172a; }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
      .card { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 15px 35px rgba(15,23,42,0.08); border: 1px solid #e2e8f0; }
      table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; }
      th { background: #e2e8f0; text-align: left; padding: 12px; font-weight: 600; }
      td { padding: 12px; border-bottom: 1px solid #e2e8f0; }
      .badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 12px; background: #e0e7ff; color: #312e81; }
      .recommendation { margin-top: 10px; padding: 12px; border-left: 4px solid #2563eb; background: #edf2ff; border-radius: 6px; }
      .section { margin-top: 36px; }
      .small { color: #475569; font-size: 14px; }
      .priority-high { color: #b91c1c; }
      .priority-medium { color: #92400e; }
      .priority-low { color: #166534; }
    </style>
  </head>
  <body>
    <h1>{{ summary.portfolio_name }}</h1>
    <p class="small">
      Season analysed: <strong>{{ summary.season }}</strong> · Buildings: {{ summary.building_count }} ·
      Monitored rooms: {{ summary.monitored_rooms }}/{{ summary.room_count }} ({{ summary.monitoring_rate }}%)
    </p>

    <div class="grid">
      <div class="card">
        <h3>Portfolio snapshot</h3>
        <p>EN 16798 analysis ran on {{ summary.monitored_rooms }} rooms across {{ summary.building_count }} building(s).</p>
        <p><strong>Portfolio Category: {{ summary.portfolio_category or "Below Category IV" }}</strong></p>
        <h4 class="small">Category Distribution</h4>
        <table class="small">
          <tr>
            <th>Category I</th><td>{{ summary.category_counts.I }} rooms ({{ summary.category_percentages.I }}%)</td>
          </tr>
          <tr>
            <th>Category II</th><td>{{ summary.category_counts.II }} rooms ({{ summary.category_percentages.II }}%)</td>
          </tr>
          <tr>
            <th>Category III</th><td>{{ summary.category_counts.III }} rooms ({{ summary.category_percentages.III }}%)</td>
          </tr>
          <tr>
            <th>Category IV</th><td>{{ summary.category_counts.IV }} rooms ({{ summary.category_percentages.IV }}%)</td>
          </tr>
        </table>
      </div>
      <div class="card">
        <h3>Primary focus</h3>
        <ul class="small">
          <li>Current monitoring coverage: {{ summary.monitoring_rate }}%. Aim for 95%+ coverage.</li>
          <li>Address worst-performing rooms highlighted below.</li>
          <li>Follow scenario playbooks (ventilation, solar shading) for rapid improvements.</li>
        </ul>
      </div>
    </div>

    <div class="section">
      <h2>Building overview</h2>
      <div class="grid">
        {% for building in building_rows %}
          <div class="card">
            <h3>{{ building.building_name }}</h3>
            <p class="small">Category: <strong>{{ building.achieved_category or "Below Category IV" }}</strong></p>
            <p class="small">Rooms monitored: {{ building.rooms_monitored }}/{{ building.rooms_total }}</p>
            <p class="small">Avg temp compliance: {{ building.avg_temp_compliance or "n/a" }}%</p>
            <p class="small">Avg CO₂ compliance: {{ building.avg_co2_compliance or "n/a" }}%</p>
            
            <h4 class="small">Category Distribution</h4>
            <div class="small">
              Cat I: {{ building.category_percentages.I }}%, 
              Cat II: {{ building.category_percentages.II }}%, 
              Cat III: {{ building.category_percentages.III }}%, 
              Cat IV: {{ building.category_percentages.IV }}%
            </div>
            
            {% if building.key_recommendations %}
              <div class="small">
                <strong>Immediate actions</strong>
                <ul>
                  {% for rec in building.key_recommendations %}
                    <li><span class="priority-{{ rec.priority }}">{{ rec.title }}</span></li>
                  {% endfor %}
                </ul>
              </div>
            {% endif %}
          </div>
        {% endfor %}
      </div>
    </div>

    {% if worst_rooms %}
      <div class="section">
        <h2>Rooms needing attention</h2>
        <table>
          <thead>
            <tr>
              <th>Building</th>
              <th>Room</th>
              <th>Temp compliance</th>
              <th>CO₂ compliance</th>
              <th>Category</th>
            </tr>
          </thead>
          <tbody>
            {% for item in worst_rooms %}
              <tr>
                <td>{{ item.building_name }}</td>
                <td>{{ item.room_name }}</td>
                <td>{{ "%.1f"|format(item.temperature_compliance or 0.0) }}%</td>
                <td>{{ "%.1f"|format(item.co2_compliance or 0.0) }}%</td>
                <td>{{ item.achieved_category or "n/a" }}</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    {% endif %}

    {% if charts.building_temperature %}
      <div class="section">{{ charts.building_temperature | safe }}</div>
    {% endif %}
    {% if charts.room_temperature %}
      <div class="section">{{ charts.room_temperature | safe }}</div>
    {% endif %}

    <div class="section">
      <h2>Room-by-room insights</h2>
      {% for row in room_rows %}
        <div class="card">
          <h3>{{ row.room_name }} <span class="badge">{{ row.building_name }}</span></h3>
          <p class="small">
            EN 16798 category: <strong>{{ row.achieved_category or "Below Category IV" }}</strong> ·
            Temperature compliance: {{ row.compliance.temperature or "n/a" }}% ·
            CO₂ compliance: {{ row.compliance.co2 or "n/a" }}%
          </p>

          {% if row.data_quality %}
            <h4>Data Quality</h4>
            <table class="small">
              {% for param, quality in row.data_quality.items() %}
                <tr>
                  <th>{{ param|capitalize }}</th>
                  <td>
                    {{ quality.completeness_percentage }}% complete, 
                    {{ quality.num_gaps }} gaps
                    {% if quality.outliers and quality.outliers.iqr %}
                      , {{ quality.outliers.iqr.count }} outliers (IQR)
                    {% endif %}
                  </td>
                </tr>
              {% endfor %}
            </table>
          {% endif %}

          <h4>Correlations</h4>
          <table>
            <tr><th>Temp vs outdoor</th><td>{{ "%.2f"|format(row.correlations.temperature_vs_outdoor or 0.0) }}</td></tr>
            <tr><th>Temp vs solar</th><td>{{ "%.2f"|format(row.correlations.temperature_vs_solar or 0.0) }}</td></tr>
            <tr><th>CO₂ vs outdoor</th><td>{{ "%.2f"|format(row.correlations.co2_vs_outdoor or 0.0) }}</td></tr>
          </table>

          {% if row.ventilation %}
            <h4>Ventilation</h4>
            <p class="small">{{ row.ventilation.description }}</p>
          {% endif %}

          {% if row.scenarios %}
            <h4>Scenarios</h4>
            <table>
              <tr><th>Scenario</th><th>Impact</th></tr>
              {% for scenario in row.scenarios %}
                <tr>
                  <td>{{ scenario.name }}</td>
                  <td>
                    {% for metric, value in scenario.metrics.items() %}
                      {{ metric }}: {{ value }}{% if not loop.last %}, {% endif %}
                    {% endfor %}
                  </td>
                </tr>
              {% endfor %}
            </table>
          {% endif %}

          {% if row.recommendations %}
            <h4>Recommendations</h4>
            {% for rec in row.recommendations %}
              <div class="recommendation">
                <strong>{{ rec.title }}</strong>
                <span class="small priority-{{ rec.priority }}">{{ rec.priority|capitalize }}</span>
                <p>{{ rec.description }}</p>
                {% if rec.expected_benefit %}<p class="small"><em>Benefit:</em> {{ rec.expected_benefit }}</p>{% endif %}
              </div>
            {% endfor %}
          {% endif %}
        </div>
      {% endfor %}
    </div>
  </body>
</html>
            """
        )

        return template.render(
            portfolio=portfolio,
            summary=summary,
            building_rows=building_rows,
            room_rows=room_rows,
            building_results=building_results,
            charts=charts,
            worst_rooms=worst_rooms,
        )

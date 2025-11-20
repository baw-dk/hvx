"""
JSON Export Service

Exports complete portfolio data structure with nested analysis results,
from portfolio level down to individual rooms and sensors.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from core.entities import Building, Floor, Portfolio, Room
from core.data_quality import analyze_dataframe_quality

import pandas as pd


class JSONExportService:
    """
    Exports complete portfolio hierarchy with all analysis results to JSON format.
    
    Structure:
    Portfolio
    └── Buildings
        └── Floors
            └── Rooms
                └── Sensors (timeseries data + quality metrics)
                    └── Analysis Results (EN16798, TAIL, BR18, etc.)
    """
    
    def __init__(
        self,
        include_timeseries: bool = False,
        include_raw_data: bool = False,
        max_timeseries_points: Optional[int] = 1000,
        season: str = "winter",
        run_analysis: bool = True,
    ):
        """
        Initialize the JSON export service.
        
        Args:
            include_timeseries: Include full timeseries data in export
            include_raw_data: Include raw sensor values (can be large)
            max_timeseries_points: Maximum number of timeseries points to include
            season: Season for EN16798 analysis ('winter' or 'summer')
            run_analysis: Whether to run standards analysis (EN16798, TAIL, BR18) before exporting.
                         Timeseries are automatically normalized to handle length mismatches.
        """
        self.include_timeseries = include_timeseries
        self.include_raw_data = include_raw_data
        self.max_timeseries_points = max_timeseries_points
        self.season = season
        self.run_analysis = run_analysis
    
    def export_portfolio(
        self,
        portfolio: Portfolio,
        buildings: Dict[str, Building],
        floors: Dict[str, Floor],
        rooms: Dict[str, Room],
        output_path: Path,
    ) -> Path:
        """
        Export complete portfolio to JSON file.
        
        Args:
            portfolio: Portfolio entity
            buildings: Dictionary of buildings by ID
            floors: Dictionary of floors by ID
            rooms: Dictionary of rooms by ID
            output_path: Output JSON file path
        
        Returns:
            Path to created JSON file
        """
        # Run analysis if requested
        if self.run_analysis:
            self._run_analysis(buildings, floors, rooms)
        
        portfolio_data = self._export_portfolio_data(
            portfolio=portfolio,
            buildings=buildings,
            floors=floors,
            rooms=rooms,
        )
        
        # Write to file with pretty formatting
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open('w', encoding='utf-8') as f:
            json.dump(portfolio_data, f, indent=2, ensure_ascii=False, default=str)
        
        return output_path
    
    def _run_analysis(
        self,
        buildings: Dict[str, Building],
        floors: Dict[str, Floor],
        rooms: Dict[str, Room],
    ) -> None:
        """Run EN16798 analysis on all buildings and rooms."""
        # Build entity lookup
        entity_registry = {}
        entity_registry.update(buildings)
        entity_registry.update(floors)
        entity_registry.update(rooms)
        entity_lookup = lambda id: entity_registry.get(id)
        
        # Normalize room timeseries to handle mismatched lengths
        for room in rooms.values():
            if room.has_data:
                self._normalize_room_timeseries(room)
        
        # Run building-level analysis
        for building in buildings.values():
            # Skip if already computed
            if building.computed_metrics.get("standards_results"):
                continue
            
            # Run standards analysis
            building.compute_standards(
                floor_lookup=floors.get,
                room_lookup=rooms.get,
                season=self.season,
                force_recompute=False,
            )
        
        # Run room-level analysis
        for room in rooms.values():
            # Skip if no data or already computed
            if not room.has_data:
                continue
            if room.computed_metrics.get("standards_results"):
                continue
                
            # Run standards analysis on room
            room.compute_standards(
                season=self.season,
                force_recompute=False,
                entity_lookup=entity_lookup,
            )
    
    def _normalize_room_timeseries(self, room: Room) -> None:
        """
        Normalize room timeseries to handle mismatched lengths.
        Truncates all timeseries and timestamps to the minimum length.
        """
        if not room.timeseries_data:
            return
        
        # Find minimum length across all timeseries
        lengths = []
        for values in room.timeseries_data.values():
            if isinstance(values, list):
                lengths.append(len(values))
        
        if not lengths:
            return
        
        min_len = min(lengths)
        
        # Truncate all timeseries to minimum length
        updated = {}
        for key, values in room.timeseries_data.items():
            if isinstance(values, list) and len(values) > min_len:
                updated[key] = values[:min_len]
            else:
                updated[key] = values
        
        room.timeseries_data = updated
        
        # Truncate timestamps to match
        if room.timestamps and len(room.timestamps) > min_len:
            room.timestamps = room.timestamps[:min_len]
    
    def _export_portfolio_data(
        self,
        portfolio: Portfolio,
        buildings: Dict[str, Building],
        floors: Dict[str, Floor],
        rooms: Dict[str, Room],
    ) -> Dict[str, Any]:
        """Export portfolio with full hierarchy."""
        
        # Export all buildings (use buildings dict, not portfolio.building_ids which may be empty)
        buildings_data = []
        for building_id, building in buildings.items():
            buildings_data.append(
                self._export_building_data(building, floors, rooms)
            )
        
        # Portfolio-level analysis results
        portfolio_analysis = self._extract_portfolio_analysis(portfolio, buildings, rooms)
        
        return {
            "portfolio": {
                "id": portfolio.id,
                "name": portfolio.name,
                "description": getattr(portfolio, 'description', None),
                "country": portfolio.country,
                "region": portfolio.region,
                "area_m2": portfolio.area_m2,
                "metadata": portfolio.metadata or {},
                "created_at": getattr(portfolio, 'created_at', None).isoformat() if getattr(portfolio, 'created_at', None) is not None else None,
                "updated_at": getattr(portfolio, 'updated_at', None).isoformat() if getattr(portfolio, 'updated_at', None) is not None else None,
                
                # Summary statistics
                "statistics": {
                    "total_buildings": len(portfolio.building_ids),
                    "total_rooms": len(rooms),
                    "total_area_m2": sum(b.area_m2 for b in buildings.values() if b.area_m2),
                },
                
                # Portfolio-level analysis
                "analysis": portfolio_analysis,
                
                # Nested buildings
                "buildings": buildings_data,
            },
            
            # Export metadata
            "export_info": {
                "timestamp": datetime.now().isoformat(),
                "version": "1.0",
                "include_timeseries": self.include_timeseries,
                "include_raw_data": self.include_raw_data,
            }
        }
    
    def _export_building_data(
        self,
        building: Building,
        floors: Dict[str, Floor],
        rooms: Dict[str, Room],
    ) -> Dict[str, Any]:
        """Export building with floors and rooms."""
        
        # Export floors
        floors_data = []
        for floor_id in building.floor_ids:
            floor = floors.get(floor_id)
            if floor:
                floors_data.append(
                    self._export_floor_data(floor, rooms)
                )
        
        # Export rooms directly under building (no floor)
        # Note: building.room_ids may be empty, so we iterate all rooms and filter by building_id
        direct_rooms_data = []
        for room in rooms.values():
            if room.building_id == building.id and not room.floor_id:
                direct_rooms_data.append(self._export_room_data(room))
        
        # Building-level analysis
        building_analysis = self._extract_building_analysis(building, rooms)
        
        return {
            "id": building.id,
            "name": building.name,
            "description": getattr(building, 'description', None),
            "building_type": building.building_type,
            "country": building.country,
            "region": building.region,
            "area_m2": building.area_m2,
            "year_built": building.year_built,
            
            # Location
            "location": {
                "address": building.address,
                "city": building.city,
                "latitude": building.latitude,
                "longitude": building.longitude,
            },
            
            # Building systems
            "systems": {
                "hvac_system": building.hvac_system,
                "heating_system": building.heating_system,
                "ventilation_type": building.ventilation_type.value if building.ventilation_type else None,
            },
            
            # Energy data
            "energy": {
                "annual_heating_kwh": building.annual_heating_kwh,
                "annual_cooling_kwh": building.annual_cooling_kwh,
                "annual_electricity_kwh": building.annual_electricity_kwh,
                "annual_hot_water_kwh": building.annual_hot_water_kwh,
                "epc_rating": building.epc_rating,
            },
            
            # Statistics
            "statistics": {
                "total_floors": len(building.floor_ids),
                "total_rooms": len([r for r in rooms.values() if r.building_id == building.id]),
            },
            
            # Building-level analysis
            "analysis": building_analysis,
            
            # Nested structure
            "floors": floors_data,
            "direct_rooms": direct_rooms_data,
            
            "metadata": building.metadata or {},
        }
    
    def _export_floor_data(
        self,
        floor: Floor,
        rooms: Dict[str, Room],
    ) -> Dict[str, Any]:
        """Export floor with its rooms."""
        
        # Export rooms on this floor
        # Note: floor.room_ids may be empty, so we iterate all rooms and filter by floor_id
        rooms_data = []
        for room in rooms.values():
            if room.floor_id == floor.id:
                rooms_data.append(self._export_room_data(room))
        
        return {
            "id": floor.id,
            "name": floor.name,
            "description": getattr(floor, 'description', None),
            "floor_number": floor.floor_number,
            "area_m2": floor.area_m2,
            
            "statistics": {
                "total_rooms": len(floor.room_ids),
            },
            
            "rooms": rooms_data,
            "metadata": floor.metadata or {},
        }
    
    def _export_room_data(self, room: Room) -> Dict[str, Any]:
        """Export room with sensors and analysis."""
        
        # Export sensors/timeseries data
        sensors_data = self._export_sensors_data(room)
        
        # Room-level analysis
        room_analysis = self._extract_room_analysis(room)
        
        # Data quality metrics
        data_quality = self._calculate_data_quality(room)
        
        return {
            "id": room.id,
            "name": room.name,
            "description": getattr(room, 'description', None),
            "room_type": room.room_type,
            "area_m2": room.area_m2,
            "volume_m3": room.volume_m3,
            "design_occupancy": room.design_occupancy,
            "ventilation_type": room.ventilation_type.value if room.ventilation_type else None,
            
            # Parent references
            "floor_id": room.floor_id,
            "building_id": room.building_id,
            
            # Data availability
            "has_data": room.has_data,
            "available_metrics": room.available_metrics,
            "data_points": len(room.timestamps) if room.timestamps else 0,
            
            # Sensors and timeseries
            "sensors": sensors_data,
            
            # Data quality
            "data_quality": data_quality,
            
            # Analysis results
            "analysis": room_analysis,
            
            "metadata": room.metadata or {},
        }
    
    def _export_sensors_data(self, room: Room) -> List[Dict[str, Any]]:
        """Export sensor/timeseries data for a room."""
        sensors = []
        
        for metric_name, values in room.timeseries_data.items():
            sensor_data = {
                "parameter": metric_name,
                "unit": self._get_unit_for_metric(metric_name),
                "data_points": len(values) if values else 0,
            }
            
            # Statistics
            if values:
                valid_values = [v for v in values if v is not None and not pd.isna(v)]
                if valid_values:
                    sensor_data["statistics"] = {
                        "min": round(min(valid_values), 2),
                        "max": round(max(valid_values), 2),
                        "mean": round(sum(valid_values) / len(valid_values), 2),
                        "count": len(valid_values),
                        "missing": len(values) - len(valid_values),
                    }
            
            # Include timeseries if requested
            if self.include_timeseries and values:
                # Limit number of points if specified
                if self.max_timeseries_points and len(values) > self.max_timeseries_points:
                    # Sample evenly
                    step = len(values) // self.max_timeseries_points
                    sampled_indices = range(0, len(values), step)
                    sampled_values = [values[i] for i in sampled_indices]
                    sampled_timestamps = [room.timestamps[i] for i in sampled_indices] if room.timestamps else None
                else:
                    sampled_values = values
                    sampled_timestamps = room.timestamps
                
                # Convert timestamps to ISO format strings
                if sampled_timestamps:
                    sampled_timestamps = [
                        ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
                        for ts in sampled_timestamps
                    ]
                
                sensor_data["timeseries"] = {
                    "timestamps": sampled_timestamps,
                    "values": sampled_values,
                    "sampled": self.max_timeseries_points and len(values) > self.max_timeseries_points,
                }
            
            sensors.append(sensor_data)
        
        return sensors
    
    def _calculate_data_quality(self, room: Room) -> Dict[str, Any]:
        """Calculate data quality metrics for room sensors."""
        if not room.timeseries_data or not room.timestamps:
            return {}
        
        # Create DataFrame for analysis
        df_data = {}
        for metric, values in room.timeseries_data.items():
            df_data[metric] = pd.Series(values)
        
        df = pd.DataFrame(df_data)
        
        # Add timestamps if available
        if room.timestamps and len(room.timestamps) == len(df):
            df.index = pd.to_datetime(room.timestamps, errors='coerce')
        
        # Analyze quality
        quality_results = analyze_dataframe_quality(df)
        
        return {
            metric: metrics.to_dict()
            for metric, metrics in quality_results.items()
        }
    
    def _extract_portfolio_analysis(
        self,
        portfolio: Portfolio,
        buildings: Dict[str, Building],
        rooms: Dict[str, Room],
    ) -> Dict[str, Any]:
        """Extract portfolio-level analysis results."""
        analysis = {}
        
        # Get computed metrics
        if hasattr(portfolio, 'computed_metrics') and portfolio.computed_metrics:
            # Portfolio metrics
            if 'portfolio_metrics' in portfolio.computed_metrics:
                metrics = portfolio.computed_metrics['portfolio_metrics']
                
                # EN16798 results
                if 'en16798' in metrics:
                    en16798_data = metrics['en16798']
                    analysis['en16798'] = {
                        "portfolio_category": en16798_data.get('portfolio_achieved_category'),
                        "buildings_analyzed": en16798_data.get('buildings_analyzed'),
                        "total_rooms": en16798_data.get('total_rooms'),
                        "rooms_analyzed": en16798_data.get('rooms_analyzed'),
                        "category_distribution": en16798_data.get('category_distribution', {}),
                        "weighted_compliance_rate": en16798_data.get('weighted_compliance_rate'),
                        "time_in_category_I_pct": en16798_data.get('weighted_time_in_cat_I_pct'),
                        "time_in_category_II_pct": en16798_data.get('weighted_time_in_cat_II_pct'),
                        "time_in_category_III_pct": en16798_data.get('weighted_time_in_cat_III_pct'),
                        "time_in_category_IV_pct": en16798_data.get('weighted_time_in_cat_IV_pct'),
                        "total_violations": en16798_data.get('total_violations'),
                        "total_area_analyzed_m2": en16798_data.get('total_area_analyzed_m2'),
                    }
            
            # Portfolio standards results
            if 'portfolio_standards' in portfolio.computed_metrics:
                standards = portfolio.computed_metrics['portfolio_standards']
                if standards:
                    analysis['standards'] = standards
        
        return analysis
    
    def _extract_building_analysis(
        self,
        building: Building,
        rooms: Dict[str, Room],
    ) -> Dict[str, Any]:
        """Extract building-level analysis results."""
        analysis = {}
        
        if hasattr(building, 'computed_metrics') and building.computed_metrics:
            # Building metrics
            if 'building_metrics' in building.computed_metrics:
                metrics = building.computed_metrics['building_metrics']
                
                # EN16798 results
                if 'en16798' in metrics:
                    en16798_data = metrics['en16798']
                    analysis['en16798'] = {
                        "building_category": en16798_data.get('building_achieved_category'),
                        "total_rooms": en16798_data.get('total_rooms'),
                        "rooms_analyzed": en16798_data.get('rooms_analyzed'),
                        "category_distribution": en16798_data.get('category_distribution', {}),
                        "weighted_compliance_rate": en16798_data.get('weighted_compliance_rate'),
                        "time_in_category_I_pct": en16798_data.get('weighted_time_in_cat_I_pct'),
                        "time_in_category_II_pct": en16798_data.get('weighted_time_in_cat_II_pct'),
                        "time_in_category_III_pct": en16798_data.get('weighted_time_in_cat_III_pct'),
                        "time_in_category_IV_pct": en16798_data.get('weighted_time_in_cat_IV_pct'),
                        "total_violations": en16798_data.get('total_violations'),
                    }
            
            # Building standards results
            if 'building_standards' in building.computed_metrics:
                standards = building.computed_metrics['building_standards']
                if standards:
                    analysis['standards'] = standards
        
        return analysis
    
    def _extract_room_analysis(self, room: Room) -> Dict[str, Any]:
        """Extract room-level analysis results."""
        analysis = {}
        
        if hasattr(room, 'computed_metrics') and room.computed_metrics:
            # Standards results
            if 'standards_results' in room.computed_metrics:
                standards = room.computed_metrics['standards_results']
                
                # EN16798
                if 'en16798_1' in standards:
                    en16798_data = standards['en16798_1']
                    analysis['en16798'] = {
                        "achieved_category": en16798_data.get('achieved_category'),
                        "all_compliant_categories": en16798_data.get('all_compliant_categories', []),
                        "overall_compliance_rate": en16798_data.get('overall_compliance_rate'),
                        "time_in_category_I_pct": en16798_data.get('time_in_category_I_pct'),
                        "time_in_category_II_pct": en16798_data.get('time_in_category_II_pct'),
                        "time_in_category_III_pct": en16798_data.get('time_in_category_III_pct'),
                        "time_in_category_IV_pct": en16798_data.get('time_in_category_IV_pct'),
                        "time_out_of_all_categories_pct": en16798_data.get('time_out_of_all_categories_pct'),
                        "total_data_points": en16798_data.get('total_data_points'),
                        "total_violations": en16798_data.get('total_violations'),
                        "season": en16798_data.get('season'),
                        "adaptive_model_used": en16798_data.get('adaptive_model_used'),
                        "temperature_metrics": en16798_data.get('temperature_metrics'),
                        "co2_metrics": en16798_data.get('co2_metrics'),
                        "humidity_metrics": en16798_data.get('humidity_metrics'),
                    }
                
                # TAIL
                if 'tail' in standards:
                    tail_data = standards['tail']
                    analysis['tail'] = {
                        "overall_rating": tail_data.get('overall_rating'),
                        "overall_rating_label": tail_data.get('overall_rating_label'),
                        "overall_compliance_rate": tail_data.get('overall_compliance_rate'),
                        "categories": tail_data.get('categories', {}),
                        "domains": tail_data.get('domains', {}),
                    }
                
                # BR18
                if 'br18' in standards:
                    analysis['br18'] = standards['br18']
                
                # WHO
                if 'who' in standards:
                    analysis['who'] = standards['who']
            
            # Simulation results
            if 'simulation_results' in room.computed_metrics:
                simulations = room.computed_metrics['simulation_results']
                if simulations:
                    analysis['simulations'] = simulations
        
        return analysis
    
    def _get_unit_for_metric(self, metric_name: str) -> str:
        """Get unit for a metric."""
        units = {
            'temperature': '°C',
            'co2': 'ppm',
            'humidity': '%',
            'illuminance': 'lux',
            'noise': 'dB(A)',
            'occupancy': 'persons',
            'outdoor_temperature': '°C',
            'outdoor_humidity': '%',
            'solar_radiation': 'W/m²',
        }
        return units.get(metric_name.lower(), '')


__all__ = ['JSONExportService']

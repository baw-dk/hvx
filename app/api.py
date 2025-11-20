"""
FastAPI backend for the flow-editor frontend.

This API provides endpoints to:
- Create portfolio structures from the flow-editor
- Run analyses (EN 16798, TAIL, etc.)
- Retrieve results and statistics
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd

# Add root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.state import PortfolioStore
from app.analysis_runner import run_en16798_for_rooms
from core import (
    SpatialEntityType,
    BuildingType,
    RoomType,
    MetricType,
    SensorSourceType,
    EnergyCarrier,
)

# Import standards
from standards.en16798 import analysis as en16798
from standards.tail import analysis as tail_analysis, calculator as tail_calc
from standards.br18 import analysis as br18

# Import simulations
from simulations import (
    OccupancyCalculator,
    VentilationCalculator,
    RCThermalModel,
    RCModelType,
    calculate_epc_rating,
)


# Initialize FastAPI
app = FastAPI(
    title="IEQ Analytics API",
    description="Backend API for Indoor Environmental Quality Analytics",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global store (in production, use database or session management)
_store = PortfolioStore()


# --- Pydantic Models for API ---

class PortfolioCreate(BaseModel):
    name: str
    country: Optional[str] = None
    region: Optional[str] = None
    description: Optional[str] = None


class BuildingCreate(BaseModel):
    name: str
    building_type: str = "office"
    area_m2: float
    city: Optional[str] = None
    country: Optional[str] = None
    heating_carrier: str = "district_heating"
    cooling_carrier: str = "electricity"
    dhw_carrier: str = "district_heating"


class FloorCreate(BaseModel):
    building_id: str
    name: str
    floor_number: int
    area_m2: float


class RoomCreate(BaseModel):
    building_id: str
    floor_id: str
    name: str
    room_type: str = "office"
    area_m2: float


class SensorCreate(BaseModel):
    entity_type: str
    entity_id: str
    parameter: str
    metric_type: str
    unit: str
    source_type: str = "measured"
    weight: float = 1.0


class PortfolioFromFlowEditor(BaseModel):
    """Structure sent from the flow-editor"""
    name: str
    metadata: Dict[str, Any]
    buildings: List[Dict[str, Any]]


class AnalysisRequest(BaseModel):
    room_ids: List[str]
    season: str = "heating"  # "heating" or "cooling"


class TimeSeriesUpload(BaseModel):
    room_id: str
    data: List[Dict[str, Any]]  # List of {timestamp, temperature, co2, humidity, ...}


# --- API Endpoints ---

@app.get("/")
def read_root():
    return {
        "message": "IEQ Analytics API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/api/health")
def health_check():
    return {"status": "healthy"}


# Portfolio endpoints

@app.post("/api/portfolio")
def create_portfolio(portfolio: PortfolioCreate):
    """Create a new portfolio"""
    try:
        _store.create_portfolio(
            name=portfolio.name,
            country=portfolio.country,
            region=portfolio.region,
            metadata={"description": portfolio.description} if portfolio.description else {},
        )
        return {"success": True, "portfolio": {"name": portfolio.name}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/portfolio")
def get_portfolio():
    """Get current portfolio structure"""
    if not _store.portfolio:
        return {"portfolio": None}

    return {
        "portfolio": {
            "name": _store.portfolio.name,
            "country": _store.portfolio.country,
            "region": _store.portfolio.region,
            "metadata": _store.portfolio.metadata,
            "hierarchy": _store.hierarchy_dict(),
        }
    }


@app.post("/api/portfolio/from-flow-editor")
def create_portfolio_from_flow_editor(data: PortfolioFromFlowEditor):
    """
    Create portfolio structure from flow-editor.
    This endpoint receives the structure from the ZIP wizard.
    """
    try:
        # Create portfolio
        _store.create_portfolio(
            name=data.name,
            country=data.metadata.get("country"),
            region=data.metadata.get("region"),
            metadata=data.metadata,
        )

        # Helper to convert string enums
        def get_enum_value(enum_class, value: str, default):
            try:
                return getattr(enum_class, value.upper(), default)
            except:
                return default

        # Create buildings
        for building_data in data.buildings:
            building = _store.add_building(
                name=building_data["name"],
                building_type=get_enum_value(
                    BuildingType, building_data.get("metadata", {}).get("building_type", "office"), BuildingType.OFFICE
                ),
                area_m2=building_data.get("metadata", {}).get("area_m2", 1000.0),
                city=building_data.get("metadata", {}).get("city"),
                heating_carrier=get_enum_value(EnergyCarrier, "district_heating", EnergyCarrier.DISTRICT_HEATING),
                cooling_carrier=get_enum_value(EnergyCarrier, "electricity", EnergyCarrier.ELECTRICITY),
                dhw_carrier=get_enum_value(EnergyCarrier, "district_heating", EnergyCarrier.DISTRICT_HEATING),
            )

            # Create floors
            for floor_data in building_data.get("floors", []):
                # Skip default_floor if it exists
                if floor_data.get("folder") == "default_floor":
                    # For flat structures, create one default floor
                    if floor_data.get("rooms"):
                        floor = _store.add_floor(
                            building_id=building.id,
                            name="Ground Floor",
                            floor_number=0,
                            area_m2=building_data.get("metadata", {}).get("area_m2", 1000.0),
                        )
                        # Create rooms
                        for room_data in floor_data.get("rooms", []):
                            room = _store.add_room(
                                building_id=building.id,
                                floor_id=floor.id,
                                name=room_data["name"],
                                room_type=get_enum_value(RoomType, room_data.get("metadata", {}).get("room_type", "office"), RoomType.OFFICE),
                                area_m2=room_data.get("metadata", {}).get("area_m2", 50.0),
                            )
                    continue

                floor = _store.add_floor(
                    building_id=building.id,
                    name=floor_data["name"],
                    floor_number=floor_data.get("metadata", {}).get("floor_number", 0),
                    area_m2=floor_data.get("metadata", {}).get("area_m2", building.area_m2),
                )

                # Create rooms
                for room_data in floor_data.get("rooms", []):
                    room = _store.add_room(
                        building_id=building.id,
                        floor_id=floor.id,
                        name=room_data["name"],
                        room_type=get_enum_value(RoomType, room_data.get("metadata", {}).get("room_type", "office"), RoomType.OFFICE),
                        area_m2=room_data.get("metadata", {}).get("area_m2", 50.0),
                    )

                    # TODO: Load sensor data from CSV if available
                    # For now, sensors would need to be uploaded separately

        return {
            "success": True,
            "portfolio": _store.hierarchy_dict(),
            "message": f"Created portfolio '{data.name}' with {len(data.buildings)} buildings",
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))


# Building endpoints

@app.post("/api/buildings")
def create_building(building: BuildingCreate):
    """Add a building to the portfolio"""
    if not _store.portfolio:
        raise HTTPException(status_code=400, detail="Create a portfolio first")

    try:
        result = _store.add_building(
            name=building.name,
            building_type=getattr(BuildingType, building.building_type.upper(), BuildingType.OFFICE),
            area_m2=building.area_m2,
            city=building.city,
            heating_carrier=getattr(EnergyCarrier, building.heating_carrier.upper(), EnergyCarrier.DISTRICT_HEATING),
            cooling_carrier=getattr(EnergyCarrier, building.cooling_carrier.upper(), EnergyCarrier.ELECTRICITY),
            dhw_carrier=getattr(EnergyCarrier, building.dhw_carrier.upper(), EnergyCarrier.DISTRICT_HEATING),
        )
        return {"success": True, "building_id": result.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# Analysis endpoints

@app.post("/api/analysis/en16798")
def run_en16798_analysis(request: AnalysisRequest):
    """Run EN 16798 analysis on selected rooms"""
    try:
        # Get rooms
        rooms = [_store.rooms[room_id] for room_id in request.room_ids if room_id in _store.rooms]

        if not rooms:
            raise HTTPException(status_code=400, detail="No valid rooms found")

        # Filter rooms with data
        rooms_with_data = [room for room in rooms if room.timeseries_data]

        if not rooms_with_data:
            raise HTTPException(status_code=400, detail="None of the selected rooms have timeseries data")

        # Run analysis
        results = run_en16798_for_rooms(
            rooms_with_data,
            season=request.season,
            buildings=_store.buildings,
        )

        return {
            "success": True,
            "results": results,
            "analyzed_rooms": len(rooms_with_data),
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rooms/{room_id}/timeseries")
def upload_room_timeseries(room_id: str, data: TimeSeriesUpload):
    """Upload timeseries data for a room"""
    if room_id not in _store.rooms:
        raise HTTPException(status_code=404, detail="Room not found")

    try:
        df = pd.DataFrame(data.data)
        _store.load_room_timeseries(room_id, df)
        return {
            "success": True,
            "message": f"Loaded {len(df)} records for room {room_id}",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/stats")
def get_statistics():
    """Get portfolio statistics"""
    return {
        "portfolio": _store.portfolio.name if _store.portfolio else None,
        "buildings": len(_store.buildings),
        "floors": len(_store.floors),
        "rooms": len(_store.rooms),
        "rooms_with_data": sum(1 for room in _store.rooms.values() if room.timeseries_data),
    }


# ===== TAIL ANALYSIS ENDPOINTS =====

class TAILAnalysisRequest(BaseModel):
    building_id: str
    season: str = "heating"  # "heating" or "cooling"


@app.post("/api/analysis/tail")
def run_tail_analysis(request: TAILAnalysisRequest):
    """
    Run TAIL (Traffic Light) analysis for a building.
    Returns color-coded ratings for all rooms.
    """
    try:
        if request.building_id not in _store.buildings:
            raise HTTPException(status_code=404, detail="Building not found")

        building = _store.buildings[request.building_id]

        # Get all rooms in building with data
        rooms_with_data = [
            room for room in _store.rooms.values()
            if room.building_id == building.id and room.timeseries_data
        ]

        if not rooms_with_data:
            raise HTTPException(status_code=400, detail="No rooms with data in this building")

        # Run TAIL analysis
        results = tail_analysis.run(
            rooms=rooms_with_data,
            season=request.season,
            building=building,
        )

        return {
            "success": True,
            "building_id": building.id,
            "building_name": building.name,
            "analyzed_rooms": len(rooms_with_data),
            "results": results,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analysis/tail/calculator")
def calculate_tail_rating(data: Dict[str, Any]):
    """
    Calculate TAIL rating from compliance percentages.
    Input: {"temperature": 95.5, "co2": 88.2, "humidity": 92.0}
    """
    try:
        calculator = tail_calc.TAILCalculator()

        # Convert input data to TAIL parameter results
        param_results = {}
        for param, compliance_pct in data.items():
            param_results[param] = tail_calc.TAILParameterResult(
                parameter=param,
                compliance_percentage=compliance_pct,
                rating=calculator._calculate_rating(compliance_pct),
            )

        # Calculate overall result
        overall = calculator.calculate_overall(list(param_results.values()))

        return {
            "success": True,
            "parameters": {k: v.dict() for k, v in param_results.items()},
            "overall": overall.dict(),
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ===== BR18 ANALYSIS ENDPOINTS =====

class BR18AnalysisRequest(BaseModel):
    room_ids: List[str]
    season: str = "heating"


@app.post("/api/analysis/br18")
def run_br18_analysis(request: BR18AnalysisRequest):
    """
    Run BR18 (Danish Building Regulations) analysis.
    """
    try:
        rooms = [_store.rooms[room_id] for room_id in request.room_ids if room_id in _store.rooms]

        if not rooms:
            raise HTTPException(status_code=400, detail="No valid rooms found")

        rooms_with_data = [room for room in rooms if room.timeseries_data]

        if not rooms_with_data:
            raise HTTPException(status_code=400, detail="None of the selected rooms have data")

        # Run BR18 analysis
        results = br18.run(
            rooms=rooms_with_data,
            season=request.season,
            buildings=_store.buildings,
        )

        return {
            "success": True,
            "analyzed_rooms": len(rooms_with_data),
            "results": results,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ===== SIMULATION ENDPOINTS =====

class OccupancySimulationRequest(BaseModel):
    room_id: str
    co2_threshold: float = 800.0  # ppm


@app.post("/api/simulations/occupancy")
def simulate_occupancy(request: OccupancySimulationRequest):
    """
    Infer occupancy patterns from CO2 data.
    """
    try:
        if request.room_id not in _store.rooms:
            raise HTTPException(status_code=404, detail="Room not found")

        room = _store.rooms[request.room_id]

        if not room.timeseries_data:
            raise HTTPException(status_code=400, detail="Room has no timeseries data")

        df = room.timeseries_data

        # Check if CO2 column exists
        co2_col = None
        for col in df.columns:
            if 'co2' in col.lower():
                co2_col = col
                break

        if not co2_col:
            raise HTTPException(status_code=400, detail="No CO2 data found")

        # Run occupancy calculation
        calculator = OccupancyCalculator()
        result = calculator.infer_from_co2(
            df[co2_col],
            co2_threshold=request.co2_threshold,
        )

        return {
            "success": True,
            "room_id": room.id,
            "room_name": room.name,
            "occupancy_pattern": result.dict() if hasattr(result, 'dict') else str(result),
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


class VentilationSimulationRequest(BaseModel):
    room_id: str
    room_volume_m3: float


@app.post("/api/simulations/ventilation")
def simulate_ventilation(request: VentilationSimulationRequest):
    """
    Calculate ventilation rates from CO2 decay.
    """
    try:
        if request.room_id not in _store.rooms:
            raise HTTPException(status_code=404, detail="Room not found")

        room = _store.rooms[request.room_id]

        if not room.timeseries_data:
            raise HTTPException(status_code=400, detail="Room has no timeseries data")

        df = room.timeseries_data

        # Find CO2 column
        co2_col = None
        for col in df.columns:
            if 'co2' in col.lower():
                co2_col = col
                break

        if not co2_col:
            raise HTTPException(status_code=400, detail="No CO2 data found")

        # Run ventilation calculation
        calculator = VentilationCalculator()
        result = calculator.calculate_from_co2_decay(
            df[co2_col],
            room_volume=request.room_volume_m3,
        )

        return {
            "success": True,
            "room_id": room.id,
            "room_name": room.name,
            "ventilation_result": result.dict() if hasattr(result, 'dict') else str(result),
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


class RCThermalSimulationRequest(BaseModel):
    room_id: str
    model_type: str = "2R2C"  # "2R2C", "3R2C", etc.


@app.post("/api/simulations/rc-thermal")
def simulate_rc_thermal(request: RCThermalSimulationRequest):
    """
    Fit RC thermal model to identify building thermal parameters.
    """
    try:
        if request.room_id not in _store.rooms:
            raise HTTPException(status_code=404, detail="Room not found")

        room = _store.rooms[request.room_id]

        if not room.timeseries_data:
            raise HTTPException(status_code=400, detail="Room has no timeseries data")

        df = room.timeseries_data

        # Find required columns
        temp_col = None
        for col in df.columns:
            if 'temp' in col.lower():
                temp_col = col
                break

        if not temp_col:
            raise HTTPException(status_code=400, detail="No temperature data found")

        # Run RC thermal model
        model_type_enum = getattr(RCModelType, request.model_type.upper(), RCModelType.TWO_R_TWO_C)
        model = RCThermalModel(model_type=model_type_enum)

        result = model.fit(
            indoor_temp=df[temp_col],
            # Add outdoor_temp and heat_input if available
        )

        return {
            "success": True,
            "room_id": room.id,
            "room_name": room.name,
            "model_type": request.model_type,
            "result": result.dict() if hasattr(result, 'dict') else str(result),
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/simulations/epc")
def calculate_epc(building_id: str):
    """
    Calculate EPC (Energy Performance Certificate) rating.
    """
    try:
        if building_id not in _store.buildings:
            raise HTTPException(status_code=404, detail="Building not found")

        building = _store.buildings[building_id]

        # Calculate EPC rating
        rating = calculate_epc_rating(building)

        return {
            "success": True,
            "building_id": building.id,
            "building_name": building.name,
            "epc_rating": rating,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ===== BATCH ANALYSIS ENDPOINT =====

class BatchAnalysisRequest(BaseModel):
    building_ids: Optional[List[str]] = None  # If None, analyze all buildings
    analyses: List[str] = ["en16798", "tail", "br18"]  # Which analyses to run
    season: str = "heating"


@app.post("/api/analysis/batch")
def run_batch_analysis(request: BatchAnalysisRequest):
    """
    Run multiple analyses on multiple buildings at once.
    This is the main endpoint the flow-editor will call.
    """
    try:
        # Determine which buildings to analyze
        if request.building_ids:
            buildings = [_store.buildings[bid] for bid in request.building_ids if bid in _store.buildings]
        else:
            buildings = list(_store.buildings.values())

        if not buildings:
            raise HTTPException(status_code=400, detail="No valid buildings found")

        results = {
            "success": True,
            "analyzed_buildings": len(buildings),
            "building_results": {},
        }

        # Run analyses for each building
        for building in buildings:
            building_results = {
                "building_id": building.id,
                "building_name": building.name,
                "analyses": {},
            }

            # Get rooms with data
            rooms_with_data = [
                room for room in _store.rooms.values()
                if room.building_id == building.id and room.timeseries_data
            ]

            if not rooms_with_data:
                building_results["error"] = "No rooms with data"
                results["building_results"][building.id] = building_results
                continue

            # Run EN 16798
            if "en16798" in request.analyses:
                try:
                    en16798_results = run_en16798_for_rooms(
                        rooms_with_data,
                        season=request.season,
                        buildings=_store.buildings,
                    )
                    building_results["analyses"]["en16798"] = en16798_results
                except Exception as e:
                    building_results["analyses"]["en16798"] = {"error": str(e)}

            # Run TAIL
            if "tail" in request.analyses:
                try:
                    tail_results = tail_analysis.run(
                        rooms=rooms_with_data,
                        season=request.season,
                        building=building,
                    )
                    building_results["analyses"]["tail"] = tail_results
                except Exception as e:
                    building_results["analyses"]["tail"] = {"error": str(e)}

            # Run BR18
            if "br18" in request.analyses:
                try:
                    br18_results = br18.run(
                        rooms=rooms_with_data,
                        season=request.season,
                        buildings=_store.buildings,
                    )
                    building_results["analyses"]["br18"] = br18_results
                except Exception as e:
                    building_results["analyses"]["br18"] = {"error": str(e)}

            results["building_results"][building.id] = building_results

        return results

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)

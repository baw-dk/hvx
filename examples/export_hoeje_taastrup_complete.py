#!/usr/bin/env python3
"""
Complete export using entity built-in methods.

Uses the entity's compute_standards() and compute_simulations() methods
to generate all analysis, then exports to JSON.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from datetime import datetime
from typing import Dict, Any

from connectors.csv.portfolio_loader import load_hoeje_taastrup


def entity_to_dict(entity, include_analysis: bool = True) -> Dict[str, Any]:
    """Convert an entity to a dictionary with all its data."""
    result = entity.get_summary()

    if include_analysis:
        # Add standards analysis if computed
        if 'standards_results' in entity.computed_metrics:
            result['standards_analysis'] = entity.computed_metrics['standards_results']
        elif 'building_standards' in entity.computed_metrics:
            result['standards_analysis'] = entity.computed_metrics['building_standards']
        elif 'floor_standards' in entity.computed_metrics:
            result['standards_analysis'] = entity.computed_metrics['floor_standards']
        elif 'portfolio_standards' in entity.computed_metrics:
            result['standards_analysis'] = entity.computed_metrics['portfolio_standards']

        # Add simulation results if computed (room-level)
        if 'simulation_results' in entity.computed_metrics:
            result['simulations'] = entity.computed_metrics['simulation_results']
        # Add building-level simulations
        elif 'building_simulations' in entity.computed_metrics:
            result['simulations'] = entity.computed_metrics['building_simulations']
        # Add floor-level simulations
        elif 'floor_simulations' in entity.computed_metrics:
            result['simulations'] = entity.computed_metrics['floor_simulations']
        # Add portfolio-level simulations
        elif 'portfolio_simulations' in entity.computed_metrics:
            result['simulations'] = entity.computed_metrics['portfolio_simulations']

        # Add analysis results if present (from old API)
        if hasattr(entity, 'analysis_results') and entity.analysis_results:
            result['legacy_analysis_results'] = {
                name: res.as_dict() if hasattr(res, 'as_dict') else str(res)
                for name, res in entity.analysis_results.items()
            }

    return result


def export_portfolio_complete(
    portfolio,
    buildings: Dict,
    floors: Dict,
    rooms: Dict,
    run_standards: bool = True,
    run_simulations: bool = True,
    country: str = 'DK',
) -> Dict[str, Any]:
    """
    Export complete portfolio using entity built-in methods.

    Args:
        portfolio: Portfolio entity
        buildings: Buildings dict
        floors: Floors dict
        rooms: Rooms dict
        run_standards: Run compute_standards on all rooms
        run_simulations: Run compute_simulations on all rooms
        country: Country code for standards

    Returns:
        Complete export dict
    """
    print("=" * 80)
    print("Hoeje-Taastrup Portfolio - Complete Export")
    print("=" * 80)
    print()

    # Create entity lookup function for hierarchy traversal
    all_entities = {**buildings, **floors, **rooms}
    all_entities[portfolio.id] = portfolio
    entity_lookup = lambda entity_id: all_entities.get(entity_id)

    # Run analysis on all rooms
    if run_standards or run_simulations:
        print("Running analysis on rooms...")
        for room_id, room in rooms.items():
            if not room.has_data:
                continue

            print(f"  Analyzing {room.name}...")

            # Compute standards (EN16798, TAIL, etc.)
            if run_standards:
                try:
                    room.compute_standards(
                        country=country,
                        season='all_year',
                        entity_lookup=entity_lookup,
                        force_recompute=True,
                    )
                except Exception as e:
                    print(f"    Standards failed: {e}")

            # Compute simulations (correlations, scenarios, etc.)
            if run_simulations:
                try:
                    room.compute_simulations(force_recompute=True, window_area_m2=15.0)
                except Exception as e:
                    print(f"    Simulations failed: {e}")

    # Compute building-level simulations
    if run_simulations:
        print("\nComputing building-level simulations...")
        for building_id, building in buildings.items():
            try:
                building.compute_simulations(
                    room_lookup=lambda rid: rooms.get(rid),
                    floor_lookup=lambda fid: floors.get(fid),
                    force_recompute=True,
                    window_area_m2=15.0,
                )
                print(f"  Building {building.name}: aggregated simulations")
            except Exception as e:
                print(f"  Building {building.name} simulations failed: {e}")

    # Compute portfolio-level simulations
    if run_simulations:
        print("\nComputing portfolio-level simulations...")
        try:
            portfolio.compute_simulations(
                building_lookup=lambda bid: buildings.get(bid),
                floor_lookup=lambda fid: floors.get(fid),
                room_lookup=lambda rid: rooms.get(rid),
                force_recompute=True,
                window_area_m2=15.0,
            )
            print(f"  Portfolio {portfolio.name}: aggregated simulations")
        except Exception as e:
            print(f"  Portfolio simulations failed: {e}")

    # Build export structure
    export_data = {
        'metadata': {
            'export_timestamp': datetime.now().isoformat(),
            'portfolio_name': portfolio.name,
            'portfolio_id': portfolio.id,
            'total_buildings': len(buildings),
            'total_floors': len(floors),
            'total_rooms': len(rooms),
            'standards_analysis_enabled': run_standards,
            'simulations_enabled': run_simulations,
            'country': country,
        },
        'portfolio': entity_to_dict(portfolio, include_analysis=True),
        'buildings': {},
    }

    # Export each building with its rooms
    print("\nExporting buildings...")
    for building_id, building in buildings.items():
        print(f"  Building: {building.name}")

        building_data = entity_to_dict(building, include_analysis=True)
        building_data['rooms'] = {}

        # Export rooms in this building
        building_rooms = {
            rid: room for rid, room in rooms.items()
            if getattr(room, 'building_id', None) == building_id
        }

        for room_id, room in building_rooms.items():
            room_data = entity_to_dict(room, include_analysis=True)
            building_data['rooms'][room_id] = room_data

        export_data['buildings'][building_id] = building_data

    return export_data


def main():
    """Main export function."""
    DATA_PATH = Path("data/samples/hoeje-taastrup")
    OUTPUT_PATH = Path("output/hoeje-taastrup-complete.json")

    print(f"Data path: {DATA_PATH}")
    print(f"Output path: {OUTPUT_PATH}")
    print()

    # Load portfolio
    print("Loading portfolio data...")
    result = load_hoeje_taastrup(DATA_PATH)

    portfolio = result.portfolio
    buildings = result.buildings
    floors = result.floors
    rooms = result.rooms

    print(f"Loaded:")
    print(f"  Portfolio: {portfolio.name}")
    print(f"  Buildings: {len(buildings)}")
    print(f"  Floors: {len(floors)}")
    print(f"  Rooms: {len(rooms)}")
    print()

    # Export with all analysis
    export_data = export_portfolio_complete(
        portfolio=portfolio,
        buildings=buildings,
        floors=floors,
        rooms=rooms,
        run_standards=True,
        run_simulations=True,
        country='DK',
    )

    # Write to file
    print("\nWriting JSON export...")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open('w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)

    file_size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)

    # Count results
    total_standards = sum(
        len(room.get('standards_analysis', {}))
        for building in export_data['buildings'].values()
        for room in building['rooms'].values()
    )

    total_simulations = sum(
        len(room.get('simulations', {}))
        for building in export_data['buildings'].values()
        for room in building['rooms'].values()
    )

    print()
    print("=" * 80)
    print("Export Complete!")
    print("=" * 80)
    print(f"Output file: {OUTPUT_PATH}")
    print(f"File size: {file_size_mb:.2f} MB")
    print(f"Buildings: {export_data['metadata']['total_buildings']}")
    print(f"Rooms: {export_data['metadata']['total_rooms']}")
    print(f"Standards results: {total_standards}")
    print(f"Simulation results: {total_simulations}")
    print()


if __name__ == "__main__":
    main()

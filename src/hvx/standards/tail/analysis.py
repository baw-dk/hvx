# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
TAIL Standard Analysis Module

Runs the TAIL rating (Thermal, Acoustic, Indoor air quality, Luminous;
Wargocki et al. 2021) for a spatial entity with
:class:`~hvx.standards.tail.calculator.TAILCalculator`, which follows the
authors' reference script tail.R. Thresholds live in config.yaml.
"""

from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, List, Optional

from hvx.core.analysis import (
    AnalysisStatus,
    AnalysisType,
    ComplianceAnalysis,
    TestResult,
)
from hvx.core.enums import StandardType
from hvx.core.rules import ApplicabilityCondition, RuleSet
from hvx.core.spacial_entity import SpatialEntity

from .calculator import TAILCalculator, TAILCategory, load_config


def create_ruleset_from_config(config: Dict[str, Any]) -> RuleSet:
    """
    RuleSet describing the TAIL assessment. TAIL labels follow per-parameter
    rules (time shares, percentiles, worst sample) that do not fit TestRule
    bounds, so the thresholds stay in config.yaml's ``parameters`` section and
    the calculator applies them; the ruleset only carries identity and scope.
    """
    applicability = config.get('applicability', {})
    conditions = [
        ApplicabilityCondition(
            id="tail_general_applicability",
            countries=applicability.get('countries'),
            regions=applicability.get('regions'),
            building_types=applicability.get('building_types'),
        )
    ]
    return RuleSet(
        id="tail_rating",
        name="TAIL Indoor Environmental Quality Rating",
        standard=StandardType.TAIL,
        category=None,  # TAIL doesn't have predefined categories
        rules=[],
        applicability_conditions=conditions,
        metadata={
            'version': config.get('version', '2024.1'),
            'reference': config.get('reference', {}),
            'domains': [d['id'] for d in config.get('domains', [])],
            'parameters': sorted((config.get('parameters') or {}).keys()),
        }
    )


def local_datetime_index(timestamps: List[Any], timezone_name: Optional[str] = None):
    """
    Parse timestamps to a naive DatetimeIndex in the building's local time.

    Timezone-aware stamps are converted to ``timezone_name`` when given, else
    kept at their own UTC offset's wall-clock time (never shifted to UTC: TAIL's
    season and opening hours are local). Naive stamps are taken as local.
    """
    import pandas as pd

    values = list(timestamps)
    try:
        index = pd.DatetimeIndex(pd.to_datetime(values, errors="coerce", format="mixed"))
    except (ValueError, TypeError):  # mixed UTC offsets
        index = None
    if index is not None:
        return TAILCalculator.to_local_index(index, timezone_name)
    stamps = []
    for value in values:
        try:
            ts = pd.Timestamp(value)
        except (ValueError, TypeError):
            stamps.append(pd.NaT)
            continue
        if ts.tzinfo is not None:
            ts = (ts.tz_convert(timezone_name) if timezone_name else ts).tz_localize(None)
        stamps.append(ts)
    return pd.DatetimeIndex(stamps)


def run(
    spatial_entity: SpatialEntity,
    timeseries_dict: Dict[str, List[float]],
    timestamps: List[str],
    custom_thresholds: Optional[Dict[str, Dict[str, float]]] = None,
    **kwargs
) -> ComplianceAnalysis:
    """
    Run TAIL rating assessment for a spatial entity.

    Args:
        spatial_entity: The spatial entity to analyze
        timeseries_dict: Dict mapping metric names to value lists
        timestamps: List of timestamp strings
        custom_thresholds: Optional overrides of config.yaml's ``parameters``
            (e.g. ``{"co2": {"outdoor_ppm": 400}}``)
        **kwargs: ``occupancy_filtered`` (True when the data is already
            restricted to occupied hours: no opening-hours filter is applied
            again), ``timezone`` (IANA name of the building's local time),
            ``outdoor_co2_ppm``, ``season`` (only used without timestamps:
            temperature bands follow each sample's month).

    Returns:
        ComplianceAnalysis object with TAIL results
    """
    from datetime import datetime

    import pandas as pd

    config = load_config()
    ruleset = create_ruleset_from_config(config)
    entity_meta = dict(getattr(spatial_entity, 'metadata', None) or {})
    tz_name = kwargs.get('timezone') or entity_meta.get('timezone') or getattr(spatial_entity, 'timezone', None)

    # Convert timeseries to pandas Series on the building's local time
    ts_data = {}
    ts_index = local_datetime_index(timestamps, tz_name) if timestamps else None
    for metric, values in timeseries_dict.items():
        if ts_index is not None and len(values) == len(ts_index):
            series = pd.Series(values, index=ts_index)
            ts_data[metric] = series[~series.index.isna()]
        else:
            ts_data[metric] = pd.Series(values)

    outdoor_co2 = kwargs.get('outdoor_co2_ppm', entity_meta.get('outdoor_co2_ppm'))
    metadata = {
        'building_type': spatial_entity.building_type,
        'room_type': spatial_entity.room_type,
        'area_m2': getattr(spatial_entity, 'area_m2', None),
        'design_occupancy': getattr(spatial_entity, 'design_occupancy', None),
        'entity_name': spatial_entity.name,
        'season_hint': kwargs.get('season'),
        'timezone': tz_name,
        'outdoor_co2_ppm': outdoor_co2,
    }

    tail_result = TAILCalculator.assess_timeseries(
        ts_data,
        custom_thresholds,
        metadata=metadata,
        building_name=spatial_entity.name,
        occupancy_filtered=bool(kwargs.get('occupancy_filtered', False)),
    )
    overall = tail_result.overall_rating

    # Create TestResult for each domain
    test_results = []
    domain_map = {
        TAILCategory.THERMAL: 'thermal',
        TAILCategory.ACOUSTIC: 'acoustic',
        TAILCategory.IAQ: 'iaq',
        TAILCategory.LUMINOUS: 'luminous',
    }

    for domain_enum, domain_name in domain_map.items():
        if domain_enum in tail_result.categories:
            domain_result = tail_result.categories[domain_enum]

            test_result = TestResult(
                id=f"test_{spatial_entity.id}_{domain_name}",
                name=f"TAIL {domain_name.title()} Assessment",
                type=AnalysisType.TEST_RESULT,
                spatial_entity_id=spatial_entity.id,
                rule_id=f"tail_{domain_name}",
                successful=domain_result.rating.value <= 2,  # Pass if Rating I or II
                out_of_range_percentage=100.0 - domain_result.compliance_rate,
                status=AnalysisStatus.COMPLETED,
                details={
                    'domain': domain_name,
                    'rating': domain_result.rating.value,
                    'rating_label': domain_result.rating_label,
                    'compliance_rate': domain_result.compliance_rate,
                    'parameter_count': domain_result.parameter_count,
                    'dominant_color': domain_result.dominant_color,
                }
            )
            test_results.append(test_result)

    # Determine overall pass (overall rating I or II)
    overall_pass = overall is not None and overall.value <= 2

    # Get rating information from config
    ratings_config = config.get('ratings', [])
    rating_info = next(
        (r for r in ratings_config if overall is not None and r['value'] == overall.value),
        {}
    )

    def payload(params):
        return {
            param.parameter: {
                'rating': param.rating_label,
                'rating_value': param.rating.value,
                'dominant_color': param.dominant_color,
                'distribution': param.distribution,
                'sample_count': param.sample_count,
                'summary_value': param.summary_value,
                'metadata': param.metadata,
            }
            for param in params
        }

    summary_results = {
        'overall_rating': overall.value if overall is not None else None,
        'overall_rating_label': tail_result.overall_rating_label,
        'overall_compliance_rate': tail_result.overall_compliance_rate,
        'rating_color': rating_info.get('color', 'unknown'),
        'rating_description': rating_info.get('description', ''),
        'domains': {
            domain_name: {
                'rating': domain_result.rating.value,
                'rating_label': domain_result.rating_label,
                'compliance_rate': domain_result.compliance_rate,
                'dominant_color': domain_result.dominant_color,
                'parameter_count': domain_result.parameter_count,
            }
            for domain_enum, domain_name in domain_map.items()
            if domain_enum in tail_result.categories
            for domain_result in [tail_result.categories[domain_enum]]
        },
        'parameters': payload(tail_result.parameter_results),
        # hvx extensions (PM10, VOC): rated, but not TAIL parameters and outside the domains
        'extensions': payload(tail_result.extensions),
        'not_rated': dict(tail_result.not_rated),
        'occupancy_filtered': bool(kwargs.get('occupancy_filtered', False)),
        'total_parameters': tail_result.total_parameters,
        'standard': 'TAIL',
        'version': config.get('version', '2024.1'),
        'visualization': tail_result.visualization,
        'graph_data': tail_result.visualization,
    }

    analysis = ComplianceAnalysis(
        id=f"compliance_{spatial_entity.id}_tail",
        name=f"TAIL Rating for {spatial_entity.name}",
        type=AnalysisType.COMPLIANCE,
        spatial_entity_id=spatial_entity.id,
        rule_set_id=ruleset.id,
        test_result_ids=[tr.id for tr in test_results],
        overall_pass=overall_pass,
        status=AnalysisStatus.COMPLETED,
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        summary_results=summary_results,
    )

    # Persist summary onto the spatial entity for downstream aggregations/visuals
    spatial_entity.computed_metrics['tail_overall_rating'] = summary_results['overall_rating']
    spatial_entity.computed_metrics['tail_overall_rating_label'] = tail_result.overall_rating_label
    spatial_entity.computed_metrics['tail_domains'] = summary_results.get('domains', {})
    spatial_entity.computed_metrics['tail_visualization'] = tail_result.visualization
    spatial_entity.tail_rating = summary_results['overall_rating']
    spatial_entity.tail_rating_label = tail_result.overall_rating_label
    spatial_entity.tail_domains = summary_results.get('domains', {})
    spatial_entity.tail_visualization = tail_result.visualization

    return analysis


# Convenience function for backward compatibility
def analyze(
    spatial_entity: SpatialEntity,
    temperature: Optional[List[float]] = None,
    co2: Optional[List[float]] = None,
    humidity: Optional[List[float]] = None,
    illuminance: Optional[List[float]] = None,
    noise: Optional[List[float]] = None,
    pm25: Optional[List[float]] = None,
    timestamps: Optional[List[str]] = None,
    custom_thresholds: Optional[Dict[str, Dict[str, float]]] = None,
) -> ComplianceAnalysis:
    """
    Convenience function for TAIL analysis.

    Args:
        spatial_entity: Entity to analyze
        temperature: Temperature values (°C)
        co2: CO2 values (ppm)
        humidity: Relative humidity values (%)
        illuminance: Illuminance values (lux)
        noise: Noise levels (dB(A))
        pm25: PM2.5 values (μg/m³)
        timestamps: Timestamp strings
        custom_thresholds: Custom threshold overrides

    Returns:
        ComplianceAnalysis with TAIL results
    """
    timeseries_dict = {}
    if temperature:
        timeseries_dict['temperature'] = temperature
    if co2:
        timeseries_dict['co2'] = co2
    if humidity:
        timeseries_dict['humidity'] = humidity
    if illuminance:
        timeseries_dict['illuminance'] = illuminance
    if noise:
        timeseries_dict['noise'] = noise
    if pm25:
        timeseries_dict['pm25'] = pm25

    return run(
        spatial_entity=spatial_entity,
        timeseries_dict=timeseries_dict,
        timestamps=timestamps or [],
        custom_thresholds=custom_thresholds,
    )


if __name__ == "__main__":
    # Test the configuration loading
    config = load_config()
    print(f"Loaded TAIL config: {config['name']}")
    print(f"Version: {config['version']}")

    # Show domains
    domains = config.get('domains', [])
    print(f"\nTAIL Domains ({len(domains)}):")
    for domain in domains:
        print(f"  - {domain['name']} ({domain['id']})")
        print(f"    Metrics: {', '.join(domain['metrics'])}")

    # Show ratings
    ratings = config.get('ratings', [])
    print(f"\nTAIL Ratings ({len(ratings)}):")
    for rating in ratings:
        print(f"  - Rating {rating['id']}: {rating['description']}")

    # Show parameter rules
    print("\nParameters:")
    for param, spec in (config.get('parameters') or {}).items():
        print(f"  - {param}: {spec.get('rule')} ({spec.get('domain')})")

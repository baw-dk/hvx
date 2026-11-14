#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Test the enhanced recommendations system with seasonal and solar analyses.

This example demonstrates:
1. Seasonal thermal analysis (winter overheating, summer undercooling)
2. Solar gain utilization analysis
3. Enhanced recommendations based on correlations and seasonal patterns
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from hvx.simulations.models.correlations import ClimateCorrelationModel
from hvx.simulations.models.recommendations import SmartRecommendationsModel
from hvx.simulations.models.scenario import ScenarioImpactModel


def generate_sample_data(
    days: int = 365,
    winter_overheating: bool = True,
    summer_undercooling: bool = True,
    poor_solar_management: bool = True,
) -> pd.DataFrame:
    """
    Generate sample environmental data with specific issues.

    Args:
        days: Number of days to generate
        winter_overheating: Add winter overheating issues
        summer_undercooling: Add summer undercooling issues
        poor_solar_management: Add poor solar management patterns
    """
    # Create hourly timestamps for a full year
    start_date = datetime(2024, 1, 1)
    timestamps = [start_date + timedelta(hours=i) for i in range(days * 24)]

    df = pd.DataFrame(index=pd.DatetimeIndex(timestamps))

    # Generate outdoor temperature (sinusoidal pattern)
    day_of_year = np.array([ts.timetuple().tm_yday for ts in timestamps])
    hour_of_day = np.array([ts.hour for ts in timestamps])

    # Seasonal pattern: cold in winter, warm in summer
    seasonal_temp = 10 + 12 * np.sin((day_of_year - 80) * 2 * np.pi / 365)

    # Daily pattern
    daily_variation = 3 * np.sin((hour_of_day - 6) * 2 * np.pi / 24)

    df["outdoor_temperature"] = seasonal_temp + daily_variation + np.random.normal(0, 1, len(timestamps))

    # Generate solar radiation
    # Higher in summer, follows daily pattern
    solar_base = 200 + 300 * np.sin((day_of_year - 80) * 2 * np.pi / 365)
    solar_daily = np.where(
        (hour_of_day >= 6) & (hour_of_day <= 18),
        np.sin((hour_of_day - 6) * np.pi / 12),
        0.0,
    )
    df["solar_radiation"] = np.maximum(0, solar_base * solar_daily + np.random.normal(0, 30, len(timestamps)))

    # Generate indoor temperature with issues
    month = np.array([ts.month for ts in timestamps])

    # Base temperature follows outdoor but with lag and insulation
    indoor_base = seasonal_temp * 0.3 + 20

    # Winter overheating (months 12, 1, 2)
    if winter_overheating:
        winter_mask = (month == 12) | (month == 1) | (month == 2)
        indoor_base[winter_mask] += 3.5  # Excessive heating

    # Summer undercooling (months 6, 7, 8)
    if summer_undercooling:
        summer_mask = (month == 6) | (month == 7) | (month == 8)
        indoor_base[summer_mask] -= 2.0  # Excessive cooling

    # Solar gains influence (poor management)
    if poor_solar_management:
        # In winter, don't capture solar gains when cold
        winter_mask = (month == 12) | (month == 1) | (month == 2)
        solar_gain_winter = np.where(winter_mask, 0, df["solar_radiation"] * 0.01)

        # In summer, let solar radiation overheat the space
        summer_mask = (month == 6) | (month == 7) | (month == 8)
        solar_gain_summer = np.where(summer_mask, df["solar_radiation"] * 0.015, 0)

        indoor_base += solar_gain_winter + solar_gain_summer
    else:
        # Good solar management
        indoor_base += df["solar_radiation"] * 0.005

    df["temperature"] = indoor_base + np.random.normal(0, 0.5, len(timestamps))

    # Generate CO2 (for completeness)
    df["co2"] = 400 + 200 * np.random.rand(len(timestamps))

    # Generate humidity
    df["humidity"] = 40 + 20 * np.random.rand(len(timestamps))

    return df


def main():
    """Run the enhanced recommendations test."""
    print("=" * 80)
    print("Enhanced Recommendations System Test")
    print("=" * 80)

    # Generate sample data with issues
    print("\nGenerating sample data with:")
    print("  - Winter overheating")
    print("  - Summer undercooling")
    print("  - Poor solar management")

    df = generate_sample_data(
        days=365,
        winter_overheating=True,
        summer_undercooling=True,
        poor_solar_management=True,
    )

    print(f"\nData shape: {df.shape}")
    print(f"Date range: {df.index[0]} to {df.index[-1]}")
    print(f"\nColumns: {', '.join(df.columns)}")

    # Run correlation analysis with enhanced features
    print("\n" + "=" * 80)
    print("Running Enhanced Correlation Analysis")
    print("=" * 80)

    correlation_model = ClimateCorrelationModel(
        temperature_band=(20.0, 24.0),
        enable_seasonal_analysis=True,
        enable_solar_analysis=True,
        window_area_m2=15.0,  # 15 m² of windows
    )

    correlations = correlation_model.compute(df, window_area_m2=15.0)

    print("\nBasic Correlations:")
    print(f"  Temperature vs Outdoor: {correlations.temperature_vs_outdoor:.3f}" if correlations.temperature_vs_outdoor else "  Temperature vs Outdoor: N/A")
    print(f"  Temperature vs Solar: {correlations.temperature_vs_solar:.3f}" if correlations.temperature_vs_solar else "  Temperature vs Solar: N/A")

    # Print seasonal thermal analysis
    if correlations.seasonal_thermal:
        print("\nSeasonal Thermal Analysis:")
        st = correlations.seasonal_thermal
        print(f"  Winter:")
        print(f"    Overheating: {st.winter_overheating_percentage:.1f}% ({st.winter_overheating_hours:.0f} hours)")
        print(f"    Avg temp: {st.winter_avg_temp:.1f}°C, Max: {st.winter_max_temp:.1f}°C")
        print(f"  Summer:")
        print(f"    Undercooling: {st.summer_undercooling_percentage:.1f}% ({st.summer_undercooling_hours:.0f} hours)")
        print(f"    Avg temp: {st.summer_avg_temp:.1f}°C, Min: {st.summer_min_temp:.1f}°C")

    # Print solar gain utilization analysis
    if correlations.solar_gain_utilization:
        print("\nSolar Gain Utilization Analysis:")
        sg = correlations.solar_gain_utilization
        print(f"  Winter:")
        print(f"    Missed opportunities: {sg.winter_solar_gain_opportunity_percentage:.1f}% ({sg.winter_solar_gain_opportunity_hours:.0f} hours)")
        print(f"    Missed heating offset: {sg.winter_missed_heating_offset_kwh:.0f} kWh" if sg.winter_missed_heating_offset_kwh else "    Missed heating offset: N/A")
        print(f"  Summer:")
        print(f"    Excess solar: {sg.summer_excess_solar_percentage:.1f}% ({sg.summer_excess_solar_hours:.0f} hours)")
        print(f"    Excess cooling load: {sg.summer_excess_cooling_load_kwh:.0f} kWh" if sg.summer_excess_cooling_load_kwh else "    Excess cooling load: N/A")
        print(f"  Annual solar utilization efficiency: {sg.annual_solar_utilization_efficiency:.1f}%")

    # Generate recommendations
    print("\n" + "=" * 80)
    print("Generating Smart Recommendations")
    print("=" * 80)

    # Calculate compliance metrics
    temp_lower, temp_upper = 20.0, 24.0
    temp_violations = ((df["temperature"] < temp_lower) | (df["temperature"] > temp_upper)).sum()
    temp_compliance = (1 - temp_violations / len(df)) * 100

    compliance = {
        "temperature": temp_compliance,
        "co2": 95.0,  # Dummy value
        "humidity": 92.0,  # Dummy value
    }

    # Run scenario analysis
    scenario_model = ScenarioImpactModel()
    scenarios = scenario_model.estimate_impacts(df, None)

    # Generate recommendations
    rec_model = SmartRecommendationsModel()
    recommendations = rec_model.generate(
        room_name="Test Room",
        compliance=compliance,
        correlations=correlations,
        ventilation_result=None,
        scenarios=scenarios,
    )

    print(f"\nGenerated {len(recommendations)} recommendations:\n")

    for i, rec in enumerate(recommendations, 1):
        print(f"{i}. [{rec.priority.upper()}] {rec.title}")
        print(f"   Type: {rec.type}")
        print(f"   {rec.description}")
        if rec.expected_benefit:
            print(f"   Expected benefit: {rec.expected_benefit}")
        print(f"   Evidence: {rec.evidence}")
        print()

    # Export results as JSON
    print("=" * 80)
    print("JSON Export Sample")
    print("=" * 80)

    results = {
        "correlations": correlations.as_dict(),
        "recommendations": [rec.as_dict() for rec in recommendations],
    }

    import json
    print(json.dumps(results, indent=2, default=str))

    print("\n" + "=" * 80)
    print("Test completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()

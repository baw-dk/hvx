#!/usr/bin/env python3
"""
Test the enhanced recommendations system with seasonal and solar analyses.

This example demonstrates:
1. Seasonal thermal analysis (winter overheating, summer undercooling)
2. Solar gain utilization analysis
3. Enhanced recommendations based on correlations and seasonal patterns
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Direct imports to avoid circular dependencies
from hvx.simulations.models.correlations.model import ClimateCorrelationModel
from hvx.simulations.models.correlations.seasonal_thermal_analysis import SeasonalThermalAnalyzer
from hvx.simulations.models.correlations.solar_gain_analysis import SolarGainUtilizationAnalyzer


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

    # Test individual analyzers
    print("\n" + "=" * 80)
    print("Testing Seasonal Thermal Analyzer")
    print("=" * 80)

    seasonal_analyzer = SeasonalThermalAnalyzer(temperature_band=(20.0, 24.0))
    seasonal_result = seasonal_analyzer.analyze(df)

    print("\nSeasonal Thermal Analysis:")
    print(f"  Winter:")
    print(f"    Overheating: {seasonal_result.winter_overheating_percentage:.1f}% ({seasonal_result.winter_overheating_hours:.0f} hours)")
    print(f"    Avg temp: {seasonal_result.winter_avg_temp:.1f}°C, Max: {seasonal_result.winter_max_temp:.1f}°C")
    print(f"  Summer:")
    print(f"    Undercooling: {seasonal_result.summer_undercooling_percentage:.1f}% ({seasonal_result.summer_undercooling_hours:.0f} hours)")
    print(f"    Avg temp: {seasonal_result.summer_avg_temp:.1f}°C, Min: {seasonal_result.summer_min_temp:.1f}°C")

    # Test solar gain analyzer
    print("\n" + "=" * 80)
    print("Testing Solar Gain Utilization Analyzer")
    print("=" * 80)

    solar_analyzer = SolarGainUtilizationAnalyzer(
        temperature_band=(20.0, 24.0),
        window_area_m2=15.0,
    )
    solar_result = solar_analyzer.analyze(df)

    print("\nSolar Gain Utilization Analysis:")
    print(f"  Winter:")
    print(f"    Missed opportunities: {solar_result.winter_solar_gain_opportunity_percentage:.1f}% ({solar_result.winter_solar_gain_opportunity_hours:.0f} hours)")
    print(f"    Missed heating offset: {solar_result.winter_missed_heating_offset_kwh:.0f} kWh" if solar_result.winter_missed_heating_offset_kwh else "    Missed heating offset: N/A")
    print(f"  Summer:")
    print(f"    Excess solar: {solar_result.summer_excess_solar_percentage:.1f}% ({solar_result.summer_excess_solar_hours:.0f} hours)")
    print(f"    Excess cooling load: {solar_result.summer_excess_cooling_load_kwh:.0f} kWh" if solar_result.summer_excess_cooling_load_kwh else "    Excess cooling load: N/A")
    print(f"  Annual solar utilization efficiency: {solar_result.annual_solar_utilization_efficiency:.1f}%")

    # Run correlation analysis with enhanced features
    print("\n" + "=" * 80)
    print("Testing Enhanced Correlation Model")
    print("=" * 80)

    correlation_model = ClimateCorrelationModel(
        temperature_band=(20.0, 24.0),
        enable_seasonal_analysis=True,
        enable_solar_analysis=True,
        window_area_m2=15.0,
    )

    correlations = correlation_model.compute(df, window_area_m2=15.0)

    print("\nBasic Correlations:")
    print(f"  Temperature vs Outdoor: {correlations.temperature_vs_outdoor:.3f}" if correlations.temperature_vs_outdoor else "  Temperature vs Outdoor: N/A")
    print(f"  Temperature vs Solar: {correlations.temperature_vs_solar:.3f}" if correlations.temperature_vs_solar else "  Temperature vs Solar: N/A")

    print("\nEnhanced Analysis Included:")
    print(f"  Seasonal thermal: {'Yes' if correlations.seasonal_thermal else 'No'}")
    print(f"  Solar gain utilization: {'Yes' if correlations.solar_gain_utilization else 'No'}")

    # Export results as JSON
    print("\n" + "=" * 80)
    print("JSON Export Sample")
    print("=" * 80)

    results = correlations.as_dict()

    import json
    print(json.dumps(results, indent=2, default=str))

    print("\n" + "=" * 80)
    print("Test completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()

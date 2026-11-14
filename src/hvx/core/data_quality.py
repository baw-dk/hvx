# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Data Quality Analysis Module

Provides comprehensive data quality metrics for time series data including:
- Missing data detection
- Outlier detection with multiple algorithms
- Gap analysis (periods without data)
- Data completeness metrics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

import numpy as np
import pandas as pd
from scipy import stats


class OutlierMethod(str, Enum):
    """Outlier detection methods."""
    IQR = "iqr"  # Interquartile Range
    Z_SCORE = "z_score"  # Standard deviations
    MODIFIED_Z_SCORE = "modified_z_score"  # Median absolute deviation
    ISOLATION_FOREST = "isolation_forest"  # Machine learning approach


@dataclass
class DataGap:
    """Represents a gap (missing period) in the data."""
    start_index: int
    end_index: int
    duration_seconds: Optional[float] = None
    start_time: Optional[pd.Timestamp] = None
    end_time: Optional[pd.Timestamp] = None
    
    @property
    def duration_hours(self) -> Optional[float]:
        """Get duration in hours."""
        if self.duration_seconds:
            return self.duration_seconds / 3600
        return None
    
    @property
    def duration_days(self) -> Optional[float]:
        """Get duration in days."""
        if self.duration_seconds:
            return self.duration_seconds / 86400
        return None


@dataclass
class OutlierInfo:
    """Information about detected outliers."""
    method: OutlierMethod
    indices: List[int] = field(default_factory=list)
    values: List[float] = field(default_factory=list)
    count: int = 0
    percentage: float = 0.0
    lower_threshold: Optional[float] = None
    upper_threshold: Optional[float] = None
    
    def __post_init__(self):
        """Calculate derived metrics."""
        self.count = len(self.indices)


@dataclass
class DataQualityMetrics:
    """Comprehensive data quality metrics for a time series."""
    
    # Basic statistics
    total_points: int = 0
    valid_points: int = 0
    missing_points: int = 0
    missing_percentage: float = 0.0
    completeness_percentage: float = 0.0
    
    # Gap analysis
    gaps: List[DataGap] = field(default_factory=list)
    num_gaps: int = 0
    avg_gap_duration_hours: Optional[float] = None
    max_gap_duration_hours: Optional[float] = None
    min_gap_duration_hours: Optional[float] = None
    
    # Outlier detection results by method
    outliers_by_method: Dict[str, OutlierInfo] = field(default_factory=dict)
    
    # Data range
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    median_value: Optional[float] = None
    std_dev: Optional[float] = None
    
    # Time coverage
    start_time: Optional[pd.Timestamp] = None
    end_time: Optional[pd.Timestamp] = None
    expected_duration_hours: Optional[float] = None
    actual_duration_hours: Optional[float] = None
    
    # Sampling rate
    expected_sampling_seconds: Optional[float] = None
    actual_sampling_seconds: Optional[float] = None
    irregular_sampling: bool = False
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'total_points': self.total_points,
            'valid_points': self.valid_points,
            'missing_points': self.missing_points,
            'missing_percentage': round(self.missing_percentage, 2),
            'completeness_percentage': round(self.completeness_percentage, 2),
            'num_gaps': self.num_gaps,
            'avg_gap_duration_hours': round(self.avg_gap_duration_hours, 2) if self.avg_gap_duration_hours else None,
            'max_gap_duration_hours': round(self.max_gap_duration_hours, 2) if self.max_gap_duration_hours else None,
            'min_gap_duration_hours': round(self.min_gap_duration_hours, 2) if self.min_gap_duration_hours else None,
            'outliers': {
                method: {
                    'count': info.count,
                    'percentage': round(info.percentage, 2),
                    'lower_threshold': round(info.lower_threshold, 2) if info.lower_threshold else None,
                    'upper_threshold': round(info.upper_threshold, 2) if info.upper_threshold else None,
                }
                for method, info in self.outliers_by_method.items()
            },
            'min_value': round(self.min_value, 2) if self.min_value else None,
            'max_value': round(self.max_value, 2) if self.max_value else None,
            'mean_value': round(self.mean_value, 2) if self.mean_value else None,
            'median_value': round(self.median_value, 2) if self.median_value else None,
            'std_dev': round(self.std_dev, 2) if self.std_dev else None,
            'expected_sampling_seconds': self.expected_sampling_seconds,
            'actual_sampling_seconds': round(self.actual_sampling_seconds, 2) if self.actual_sampling_seconds else None,
            'irregular_sampling': self.irregular_sampling,
        }


class DataQualityAnalyzer:
    """Analyzes time series data quality."""
    
    def __init__(
        self,
        expected_sampling_seconds: Optional[float] = None,
        outlier_methods: Optional[List[OutlierMethod]] = None,
    ):
        """
        Initialize the analyzer.
        
        Args:
            expected_sampling_seconds: Expected sampling interval in seconds
            outlier_methods: List of outlier detection methods to use
        """
        self.expected_sampling_seconds = expected_sampling_seconds
        self.outlier_methods = outlier_methods or [
            OutlierMethod.IQR,
            OutlierMethod.Z_SCORE,
            OutlierMethod.MODIFIED_Z_SCORE,
        ]
    
    def analyze(
        self,
        data: pd.Series,
        parameter_name: Optional[str] = None,
    ) -> DataQualityMetrics:
        """
        Perform comprehensive data quality analysis.
        
        Args:
            data: Time series data (can have missing values)
            parameter_name: Name of the parameter being analyzed
        
        Returns:
            DataQualityMetrics object with all quality metrics
        """
        metrics = DataQualityMetrics()
        
        # Basic counts
        metrics.total_points = len(data)
        metrics.valid_points = data.notna().sum()
        metrics.missing_points = data.isna().sum()
        
        if metrics.total_points > 0:
            metrics.completeness_percentage = (metrics.valid_points / metrics.total_points) * 100
            metrics.missing_percentage = (metrics.missing_points / metrics.total_points) * 100
        
        # Time coverage
        if isinstance(data.index, pd.DatetimeIndex) and len(data.index) > 0:
            metrics.start_time = data.index[0]
            metrics.end_time = data.index[-1]
            total_duration = (metrics.end_time - metrics.start_time).total_seconds()
            metrics.expected_duration_hours = total_duration / 3600
            
            # Actual sampling rate
            if len(data) > 1:
                time_diffs = data.index.to_series().diff().dropna()
                median_diff = time_diffs.median()
                metrics.actual_sampling_seconds = median_diff.total_seconds() if isinstance(median_diff, pd.Timedelta) else float(median_diff)

                # Check if sampling is irregular
                if len(time_diffs) > 0:
                    std_diff = time_diffs.std()
                    std_diffs = std_diff.total_seconds() if isinstance(std_diff, pd.Timedelta) else float(std_diff)
                    if metrics.actual_sampling_seconds and metrics.actual_sampling_seconds > 0:
                        cv = std_diffs / metrics.actual_sampling_seconds
                        metrics.irregular_sampling = cv > 0.1  # More than 10% variation
            
            metrics.expected_sampling_seconds = self.expected_sampling_seconds or metrics.actual_sampling_seconds
        
        # Gap analysis
        metrics.gaps = self._detect_gaps(data)
        metrics.num_gaps = len(metrics.gaps)
        
        if metrics.gaps:
            gap_durations = [g.duration_hours for g in metrics.gaps if g.duration_hours]
            if gap_durations:
                metrics.avg_gap_duration_hours = float(np.mean(gap_durations))
                metrics.max_gap_duration_hours = float(max(gap_durations))
                metrics.min_gap_duration_hours = float(min(gap_durations))
        
        # Statistical analysis on valid data
        valid_data = data.dropna()
        if len(valid_data) > 0:
            metrics.min_value = float(valid_data.min())
            metrics.max_value = float(valid_data.max())
            metrics.mean_value = float(valid_data.mean())
            metrics.median_value = float(valid_data.median())
            metrics.std_dev = float(valid_data.std())
        
        # Outlier detection
        for method in self.outlier_methods:
            outlier_info = self._detect_outliers(valid_data, method)
            if outlier_info:
                outlier_info.percentage = (outlier_info.count / len(valid_data) * 100) if len(valid_data) > 0 else 0
                metrics.outliers_by_method[method.value] = outlier_info
        
        return metrics
    
    def _detect_gaps(self, data: pd.Series) -> List[DataGap]:
        """Detect gaps (periods of missing data) in the time series."""
        gaps = []
        
        if not isinstance(data.index, pd.DatetimeIndex):
            # For non-time-indexed data, just look for NaN sequences
            is_na = data.isna()
            gap_start = None
            
            for i, is_missing in enumerate(is_na):
                if is_missing and gap_start is None:
                    gap_start = i
                elif not is_missing and gap_start is not None:
                    gaps.append(DataGap(
                        start_index=gap_start,
                        end_index=i - 1,
                    ))
                    gap_start = None
            
            # Handle gap at the end
            if gap_start is not None:
                gaps.append(DataGap(
                    start_index=gap_start,
                    end_index=len(data) - 1,
                ))
        else:
            # For time-indexed data, detect both NaN values and time gaps
            expected_interval = self.expected_sampling_seconds or self._estimate_sampling_interval(data)
            
            if expected_interval is None:
                return gaps
            
            # Allow 50% tolerance for irregular sampling
            max_gap_threshold = expected_interval * 1.5
            
            prev_time: Optional[pd.Timestamp] = None
            gap_start_idx: Optional[int] = None
            gap_start_time: Optional[pd.Timestamp] = None

            for i in range(len(data)):
                timestamp = data.index[i]
                value = data.iloc[i]

                if prev_time is not None:
                    time_diff = (timestamp - prev_time).total_seconds()

                    # Detect time gap
                    if time_diff > max_gap_threshold:
                        if gap_start_idx is None:
                            gap_start_idx = i - 1
                            gap_start_time = prev_time

                        # Close current gap
                        gaps.append(DataGap(
                            start_index=gap_start_idx,
                            end_index=i - 1,
                            duration_seconds=time_diff,
                            start_time=gap_start_time,
                            end_time=timestamp,
                        ))
                        gap_start_idx = None
                        gap_start_time = None
                    elif pd.isna(value):
                        # Missing value
                        if gap_start_idx is None:
                            gap_start_idx = i
                            gap_start_time = timestamp
                    elif gap_start_idx is not None and not pd.isna(value):
                        # End of missing value gap
                        if gap_start_time is not None:
                            duration = (timestamp - gap_start_time).total_seconds()
                            gaps.append(DataGap(
                                start_index=gap_start_idx,
                                end_index=i - 1,
                                duration_seconds=duration,
                                start_time=gap_start_time,
                                end_time=timestamp,
                            ))
                        gap_start_idx = None
                        gap_start_time = None

                prev_time = timestamp
        
        return gaps
    
    def _estimate_sampling_interval(self, data: pd.Series) -> Optional[float]:
        """Estimate the typical sampling interval in seconds."""
        if not isinstance(data.index, pd.DatetimeIndex) or len(data) < 2:
            return None

        time_diffs = data.index.to_series().diff().dropna()
        if len(time_diffs) == 0:
            return None

        median_diff = time_diffs.median()
        return median_diff.total_seconds() if isinstance(median_diff, pd.Timedelta) else float(median_diff)
    
    def _detect_outliers(self, data: pd.Series, method: OutlierMethod) -> Optional[OutlierInfo]:
        """Detect outliers using the specified method."""
        if len(data) == 0:
            return None
        
        if method == OutlierMethod.IQR:
            return self._detect_outliers_iqr(data)
        elif method == OutlierMethod.Z_SCORE:
            return self._detect_outliers_zscore(data)
        elif method == OutlierMethod.MODIFIED_Z_SCORE:
            return self._detect_outliers_modified_zscore(data)
        elif method == OutlierMethod.ISOLATION_FOREST:
            return self._detect_outliers_isolation_forest(data)
        
        return None
    
    def _detect_outliers_iqr(self, data: pd.Series, multiplier: float = 1.5) -> OutlierInfo:
        """Detect outliers using Interquartile Range method."""
        q1 = data.quantile(0.25)
        q3 = data.quantile(0.75)
        iqr = q3 - q1
        
        lower_bound = q1 - multiplier * iqr
        upper_bound = q3 + multiplier * iqr
        
        outlier_mask = (data < lower_bound) | (data > upper_bound)
        outlier_indices = data.index[outlier_mask].tolist()
        outlier_values = data[outlier_mask].tolist()
        
        return OutlierInfo(
            method=OutlierMethod.IQR,
            indices=outlier_indices,
            values=outlier_values,
            lower_threshold=float(lower_bound),
            upper_threshold=float(upper_bound),
        )
    
    def _detect_outliers_zscore(self, data: pd.Series, threshold: float = 3.0) -> OutlierInfo:
        """Detect outliers using Z-score method."""
        mean = data.mean()
        std = data.std()
        
        if std == 0:
            return OutlierInfo(method=OutlierMethod.Z_SCORE)
        
        z_scores = np.abs((data - mean) / std)
        outlier_mask = z_scores > threshold
        outlier_indices = data.index[outlier_mask].tolist()
        outlier_values = data[outlier_mask].tolist()
        
        lower_bound = mean - threshold * std
        upper_bound = mean + threshold * std
        
        return OutlierInfo(
            method=OutlierMethod.Z_SCORE,
            indices=outlier_indices,
            values=outlier_values,
            lower_threshold=float(lower_bound),
            upper_threshold=float(upper_bound),
        )
    
    def _detect_outliers_modified_zscore(self, data: pd.Series, threshold: float = 3.5) -> OutlierInfo:
        """Detect outliers using Modified Z-score (MAD) method."""
        median = data.median()
        mad = np.median(np.abs(data - median))

        if mad == 0:
            return OutlierInfo(method=OutlierMethod.MODIFIED_Z_SCORE)

        modified_z_scores = 0.6745 * (data - median) / float(mad)
        outlier_mask = np.abs(modified_z_scores) > threshold
        outlier_indices = data.index[outlier_mask].tolist()
        outlier_values = data[outlier_mask].tolist()
        
        # Approximate bounds
        lower_bound = median - threshold * mad / 0.6745
        upper_bound = median + threshold * mad / 0.6745
        
        return OutlierInfo(
            method=OutlierMethod.MODIFIED_Z_SCORE,
            indices=outlier_indices,
            values=outlier_values,
            lower_threshold=float(lower_bound),
            upper_threshold=float(upper_bound),
        )
    
    def _detect_outliers_isolation_forest(self, data: pd.Series, contamination: float = 0.1) -> OutlierInfo:
        """Detect outliers using Isolation Forest (requires scikit-learn)."""
        try:
            from sklearn.ensemble import IsolationForest
        except ImportError:
            return OutlierInfo(method=OutlierMethod.ISOLATION_FOREST)

        if len(data) < 10:  # Need minimum samples
            return OutlierInfo(method=OutlierMethod.ISOLATION_FOREST)

        # Reshape for sklearn - convert to numpy array first to ensure reshape is available
        X = np.array(data.values).reshape(-1, 1)
        
        # Fit model
        clf = IsolationForest(contamination=contamination, random_state=42)
        predictions = clf.fit_predict(X)
        
        # -1 indicates outlier
        outlier_mask = predictions == -1
        outlier_indices = data.index[outlier_mask].tolist()
        outlier_values = data[outlier_mask].tolist()
        
        return OutlierInfo(
            method=OutlierMethod.ISOLATION_FOREST,
            indices=outlier_indices,
            values=outlier_values,
        )


def analyze_dataframe_quality(
    df: pd.DataFrame,
    expected_sampling_seconds: Optional[float] = None,
) -> Dict[str, DataQualityMetrics]:
    """
    Analyze data quality for all columns in a DataFrame.
    
    Args:
        df: DataFrame with time series data
        expected_sampling_seconds: Expected sampling interval
    
    Returns:
        Dictionary mapping column names to DataQualityMetrics
    """
    analyzer = DataQualityAnalyzer(expected_sampling_seconds=expected_sampling_seconds)
    results = {}
    
    for column in df.columns:
        if pd.api.types.is_numeric_dtype(df[column]):
            results[column] = analyzer.analyze(df[column], parameter_name=column)
    
    return results


__all__ = [
    "DataQualityAnalyzer",
    "DataQualityMetrics",
    "DataGap",
    "OutlierInfo",
    "OutlierMethod",
    "analyze_dataframe_quality",
]

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""
Air change rate from CO2 decay (tracer-gas decay method, cf. ASTM E741 / D6245).

After people leave, CO2 falls towards the background level:
``C(t) - C_bg = (C_0 - C_bg) * exp(-ACH * t)``. hvx fits
``ln(C - C_bg) = a - ACH * t`` with a free intercept on the points that follow the
peak, so the fit does not depend on when within a sampling step people left.

What the number means: decays happen when the room is empty, mostly after hours,
when mechanical ventilation may run at a reduced level or be off. The result
characterises the room *then* (infiltration / reduced ventilation), not the
ventilation during use. hvx therefore reports it as an "after-hours air change"
with the median and spread of the individual decays, and gives no quality rating.

Guards:
- Only decays in unoccupied time (``unoccupied`` mask), so nobody adds CO2.
- Background CO2 is estimated per room (5th percentile of the readings, at least
  380 ppm) instead of assuming 400 ppm.
- Decays that are too fast for the sampling interval (less than ~3 points above
  the background) are skipped; on hourly data rates above ~1 h-1 cannot be
  resolved and are reported as such.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class VentilationRateResult:
    """After-hours air change rate from CO2 decays."""
    ach: float  # median air changes per hour over the accepted decays
    ventilation_l_s: Optional[float]  # ach x volume / 3.6, if the volume is known
    r_squared: float  # median R² of the log-linear fits
    initial_co2: float  # median CO2 at the start of the decays (ppm)
    final_co2: float  # background used (ppm)
    outdoor_co2: float  # background CO2 estimated for this room (ppm)
    confidence_interval: Tuple[float, float]  # interquartile range of the decays' ACH
    quality_score: float  # share of candidate decays that were usable (0-1)
    category: str  # what the value describes, e.g. "after_hours"
    description: str
    decays: int = 0  # number of accepted decays
    too_fast: int = 0  # decays too fast to resolve at this sampling interval
    step_hours: Optional[float] = None
    resolvable_max_ach: Optional[float] = None  # fastest rate this sampling interval can resolve
    per_decay: List[float] = field(default_factory=list)


class VentilationCalculator:
    """Estimate the after-hours air change rate of a room from CO2 decays."""

    MIN_POINTS = 3  # points above background after the peak
    MIN_EXCESS_PPM = 50.0  # below this the excess is within sensor noise
    MIN_R2 = 0.9  # log-linear fit quality

    def __init__(self, outdoor_co2: Optional[float] = None):
        """``outdoor_co2``: fixed background (ppm); None estimates it from the data."""
        self.outdoor_co2 = outdoor_co2

    @staticmethod
    def estimate_background(co2: pd.Series) -> float:
        values = co2.dropna()
        if values.empty:
            return 420.0
        return float(max(380.0, np.percentile(values, 5)))

    def estimate_from_co2_decay(
        self,
        co2_series: pd.Series,
        volume_m3: Optional[float] = None,
        min_decay_threshold: float = 100.0,
        unoccupied: Optional[pd.Series] = None,
    ) -> Optional[VentilationRateResult]:
        """
        ``unoccupied``: boolean Series on the same index, True when nobody is expected
        (e.g. outside the occupancy schedule). Without it every decay is used.
        """
        co2 = co2_series.dropna().sort_index()
        if len(co2) < self.MIN_POINTS + 2 or not isinstance(co2.index, pd.DatetimeIndex):
            return None
        background = self.outdoor_co2 if self.outdoor_co2 is not None else self.estimate_background(co2)
        steps = co2.index.to_series().diff().dt.total_seconds().dropna() / 3600.0
        step = float(steps[steps > 0].median()) if (steps > 0).any() else 1.0
        if unoccupied is not None:
            unoccupied = unoccupied.reindex(co2.index).fillna(False).astype(bool)

        fits: List[Tuple[float, float, float]] = []  # (ach, r2, start ppm)
        candidates = too_fast = 0
        for segment in self._identify_decay_periods(co2, min_decay_threshold, step):
            # Drop the peak: people may have left at any time within the step after it.
            points = segment.iloc[1:]
            if unoccupied is not None and not bool(unoccupied.reindex(points.index).fillna(False).all()):
                continue
            candidates += 1
            excess = points - background
            usable = points[excess > self.MIN_EXCESS_PPM]
            if len(usable) < self.MIN_POINTS:
                too_fast += 1
                continue
            t = (usable.index - usable.index[0]).total_seconds().to_numpy() / 3600.0
            y = np.log(usable.to_numpy(dtype=float) - background)
            slope, intercept = np.polyfit(t, y, 1)
            predicted = intercept + slope * t
            ss_tot = float(np.sum((y - y.mean()) ** 2))
            r2 = 1.0 - float(np.sum((y - predicted) ** 2)) / ss_tot if ss_tot > 0 else 0.0
            ach = -float(slope)
            if ach <= 0 or r2 < self.MIN_R2:
                continue
            fits.append((ach, r2, float(segment.iloc[0])))

        if not fits:
            return None
        # Fastest decay this sampling interval can show: MIN_POINTS points still above
        # MIN_EXCESS_PPM, starting from the typical excess at the peak.
        start_excess = float(np.median([f[2] for f in fits])) - background
        resolvable = (
            round(float(np.log(start_excess / self.MIN_EXCESS_PPM) / (self.MIN_POINTS * step)), 2)
            if start_excess > self.MIN_EXCESS_PPM and step > 0 else None
        )
        rates = np.array([f[0] for f in fits])
        ach = float(np.median(rates))
        q1, q3 = (float(v) for v in np.percentile(rates, [25, 75]))
        r2 = float(np.median([f[1] for f in fits]))
        litres = ach * volume_m3 / 3.6 if volume_m3 else None
        description = (
            f"After-hours air change {ach:.2f} h-1 (median of {len(fits)} CO2 decays, interquartile range "
            f"{q1:.2f}-{q3:.2f}; background {background:.0f} ppm). Describes the empty room, not ventilation during use."
        )
        if too_fast:
            description += f" {too_fast} decay(s) were too fast to resolve at a {step:g} h sampling interval."
        return VentilationRateResult(
            ach=round(ach, 2),
            ventilation_l_s=round(litres, 1) if litres else None,
            r_squared=round(r2, 3),
            initial_co2=round(float(np.median([f[2] for f in fits])), 1),
            final_co2=round(background, 1),
            outdoor_co2=round(background, 1),
            confidence_interval=(round(q1, 2), round(q3, 2)),
            quality_score=round(len(fits) / candidates, 3) if candidates else 0.0,
            category="after_hours",
            description=description,
            decays=len(fits),
            too_fast=too_fast,
            step_hours=round(step, 3),
            resolvable_max_ach=resolvable,
            per_decay=[round(float(r), 3) for r in rates],
        )

    @staticmethod
    def _identify_decay_periods(co2: pd.Series, min_decay: float, step: float) -> List[pd.Series]:
        """Runs of falling CO2 that start at a local peak and drop by at least ``min_decay``.
        A run ends when CO2 rises again (> 5 ppm) or at a data gap (> 3 steps)."""
        values = co2.to_numpy(dtype=float)
        times = co2.index
        gap = pd.Timedelta(hours=3 * step)
        segments: List[pd.Series] = []
        i = 0
        n = len(values)
        while i < n - 1:
            if values[i + 1] < values[i]:
                j = i + 1
                while j + 1 < n and values[j + 1] <= values[j] + 5 and times[j + 1] - times[j] <= gap:
                    j += 1
                if values[i] - values[j] >= min_decay and j - i >= 2:
                    segments.append(co2.iloc[i:j + 1])
                i = j
            else:
                i += 1
        return segments

    def calculate_required_ach(
        self,
        volume_m3: float,
        required_ventilation_l_s: float
    ) -> float:
        """
        Calculate required ACH from ventilation rate.

        Args:
            volume_m3: Room volume (m³)
            required_ventilation_l_s: Required ventilation (L/s)

        Returns:
            Required air change rate (ACH)
        """
        if volume_m3 <= 0:
            return 0.0

        # Convert L/s to m³/h: L/s * 3.6 = m³/h
        ventilation_m3_h = required_ventilation_l_s * 3.6

        # ACH = m³/h / volume
        return ventilation_m3_h / volume_m3

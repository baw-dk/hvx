"""
HVX — indoor environmental quality (IEQ) analytics for buildings.

Subpackages
-----------
``hvx.core``         data model (Portfolio / Building / Floor / Room), IFC & Brick semantics
``hvx.standards``    EN 16798-1, TAIL, BR18 assessments
``hvx.simulations``  ventilation, occupancy, correlations, scenarios, recommendations
``hvx.reporting``    portfolio reports (HTML / JSON / CSV)
``hvx.live``         live data sources (Home Assistant, HTTP, in-memory) and rolling monitoring
``hvx.connectors``   file loaders (CSV)
``hvx.app``          FastAPI backend and Streamlit UI (optional extras)
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("hvx")
except PackageNotFoundError:  # running from a source checkout
    __version__ = "0.0.0+local"

__all__ = ["__version__"]

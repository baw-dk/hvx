"""
Live data for HVX.

* Sources (:mod:`.sources`): Home Assistant REST, in-memory push.
* Bindings (:mod:`.bindings`): which point feeds which room parameter,
  stored on the data model as ``SensorDefinition.sources``.
* :class:`LiveMonitor`: incremental refresh, bounded rolling window,
  live limit checks and rolling EN 16798 assessment.
* Site files (:mod:`.site`): YAML description of buildings, rooms and points.
"""

from .base import Reading, TimeSeriesSource
from .bindings import PointBinding, bind, discover_bindings
from .limits import category_now, en16798_limits
from .monitor import LiveMonitor, LiveSnapshot, ParameterNow, RoomLiveState
from .site import Site, build_source, load_site, site_skeleton
from .sources import HomeAssistantError, HomeAssistantSource, InMemorySource

__all__ = [
    "Reading",
    "TimeSeriesSource",
    "PointBinding",
    "bind",
    "discover_bindings",
    "category_now",
    "en16798_limits",
    "LiveMonitor",
    "LiveSnapshot",
    "ParameterNow",
    "RoomLiveState",
    "Site",
    "build_source",
    "load_site",
    "site_skeleton",
    "HomeAssistantSource",
    "HomeAssistantError",
    "InMemorySource",
]

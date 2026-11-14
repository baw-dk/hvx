"""Shared result container for semantic importers (IFC, Brick)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:  # pragma: no cover
    from ..entities import Building, Floor, Portfolio, Room


@dataclass
class SemanticImportResult:
    portfolio: "Portfolio"
    buildings: Dict[str, "Building"] = field(default_factory=dict)
    floors: Dict[str, "Floor"] = field(default_factory=dict)
    rooms: Dict[str, "Room"] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    source: Optional[str] = None

    def summary(self) -> Dict[str, object]:
        sensors = sum(len(g.sensors) for r in self.rooms.values() for g in r.sensor_groups.values())
        return {
            "portfolio": self.portfolio.name,
            "buildings": len(self.buildings),
            "floors": len(self.floors),
            "rooms": len(self.rooms),
            "sensors": sensors,
            "warnings": list(self.warnings),
            "source": self.source,
        }


__all__ = ["SemanticImportResult"]

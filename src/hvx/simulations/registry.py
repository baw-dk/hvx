"""
Simulations Registry

Central registry for all simulation models that can be applied to spatial entities.
Similar to the standards registry but for simulation models.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
import importlib


class SimulationCategory(str, Enum):
    """Categories of simulation models."""
    OCCUPANCY = "occupancy"
    VENTILATION = "ventilation"
    THERMAL = "thermal"
    ENERGY = "energy"
    CORRELATIONS = "correlations"
    SCENARIOS = "scenarios"
    RECOMMENDATIONS = "recommendations"


@dataclass
class SimulationConfig:
    """Configuration for a simulation model."""
    id: str
    name: str
    category: SimulationCategory
    description: str
    module_path: str
    model_class: str
    required_metrics: Set[str]
    optional_metrics: Set[str] = field(default_factory=set)
    entity_types: Set[str] = field(default_factory=lambda: {'room', 'floor', 'building', 'portfolio'})
    version: str = "1.0"

    def is_applicable(
        self,
        entity_type: str,
        available_metrics: Set[str],
    ) -> bool:
        """Check if this simulation is applicable to the given entity."""
        # Check entity type
        if entity_type.lower() not in self.entity_types:
            return False

        # Check required metrics
        if not self.required_metrics.issubset(available_metrics):
            return False

        return True


class SimulationsRegistry:
    """Registry for all simulation models."""

    def __init__(self):
        self._simulations: Dict[str, SimulationConfig] = {}
        self._register_default_simulations()

    def _register_default_simulations(self):
        """Register all default simulation models."""

        # Occupancy detection
        self.register(SimulationConfig(
            id='occupancy',
            name='Occupancy Detection',
            category=SimulationCategory.OCCUPANCY,
            description='Detect occupancy patterns from CO2 data',
            module_path='hvx.simulations.models.occupancy',
            model_class='OccupancyCalculator',
            required_metrics={'co2'},
            entity_types={'room'},
        ))

        # Ventilation rate estimation
        self.register(SimulationConfig(
            id='ventilation',
            name='Ventilation Rate Estimation',
            category=SimulationCategory.VENTILATION,
            description='Estimate air change rate from CO2 decay analysis',
            module_path='hvx.simulations.models.ventilation.model',
            model_class='VentilationCalculator',
            required_metrics={'co2'},
            entity_types={'room'},
        ))

        # Climate correlations (including seasonal and solar)
        self.register(SimulationConfig(
            id='correlations',
            name='Climate Correlations Analysis',
            category=SimulationCategory.CORRELATIONS,
            description='Analyze correlations between indoor and outdoor conditions with seasonal and solar patterns',
            module_path='hvx.simulations.models.correlations.model',
            model_class='ClimateCorrelationModel',
            required_metrics={'temperature'},
            optional_metrics={'co2', 'humidity', 'outdoor_temperature', 'solar_radiation', 'solar_irradiance'},
            entity_types={'room'},
        ))

        # Scenario simulations
        self.register(SimulationConfig(
            id='scenarios',
            name='Scenario Impact Analysis',
            category=SimulationCategory.SCENARIOS,
            description='Simulate impact of ventilation boost and solar shading scenarios',
            module_path='hvx.simulations.models.scenario.model',
            model_class='ScenarioImpactModel',
            required_metrics={'temperature'},
            optional_metrics={'co2', 'solar_radiation', 'solar_irradiance'},
            entity_types={'room'},
        ))

        # Smart recommendations
        self.register(SimulationConfig(
            id='recommendations',
            name='Smart Recommendations',
            category=SimulationCategory.RECOMMENDATIONS,
            description='Generate smart recommendations based on analysis results',
            module_path='hvx.simulations.models.recommendations.model',
            model_class='SmartRecommendationsModel',
            required_metrics=set(),  # Uses analysis results, not raw metrics
            optional_metrics={'temperature', 'co2', 'humidity'},
            entity_types={'room'},
        ))

        # RC Thermal Model
        self.register(SimulationConfig(
            id='rc_thermal',
            name='RC Thermal Model',
            category=SimulationCategory.THERMAL,
            description='Resistance-Capacitance thermal dynamics model',
            module_path='hvx.simulations.models.rc_thermal.model',
            model_class='RCThermalModel',
            required_metrics={'temperature'},
            optional_metrics={'outdoor_temperature', 'solar_radiation'},
            entity_types={'room', 'building'},
        ))

        # EPC Rating
        self.register(SimulationConfig(
            id='epc',
            name='EPC Rating Calculator',
            category=SimulationCategory.ENERGY,
            description='Calculate Energy Performance Certificate rating',
            module_path='hvx.simulations.models.real_epc',
            model_class='calculate_epc_rating',
            required_metrics=set(),  # Uses building properties
            entity_types={'building'},
        ))

    def register(self, config: SimulationConfig):
        """Register a simulation model."""
        self._simulations[config.id] = config

    def get_simulation(self, simulation_id: str) -> Optional[SimulationConfig]:
        """Get a simulation configuration by ID."""
        return self._simulations.get(simulation_id)

    def get_applicable_simulations(
        self,
        entity_type: str,
        available_metrics: Set[str],
        category: Optional[SimulationCategory] = None,
    ) -> List[SimulationConfig]:
        """
        Get all applicable simulations for an entity.

        Args:
            entity_type: Type of entity ('room', 'floor', 'building', 'portfolio')
            available_metrics: Set of available metric names
            category: Optional category filter

        Returns:
            List of applicable simulation configurations
        """
        applicable = []

        for sim_config in self._simulations.values():
            # Filter by category if specified
            if category and sim_config.category != category:
                continue

            # Check if applicable
            if sim_config.is_applicable(entity_type, available_metrics):
                applicable.append(sim_config)

        return applicable

    def load_model_class(self, module_path: str, class_name: str) -> Any:
        """Load and return a simulation model class."""
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    def list_all_simulations(self) -> List[SimulationConfig]:
        """List all registered simulations."""
        return list(self._simulations.values())

    def list_by_category(self, category: SimulationCategory) -> List[SimulationConfig]:
        """List all simulations in a category."""
        return [
            sim for sim in self._simulations.values()
            if sim.category == category
        ]


# Global registry instance
_global_registry: Optional[SimulationsRegistry] = None


def get_simulations_registry() -> SimulationsRegistry:
    """Get the global simulations registry instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = SimulationsRegistry()
    return _global_registry


def reset_simulations_registry():
    """Reset the global registry (mainly for testing)."""
    global _global_registry
    _global_registry = None


# Convenience functions
def list_simulation_models() -> List[str]:
    """List all available simulation model IDs."""
    registry = get_simulations_registry()
    return [sim.id for sim in registry.list_all_simulations()]


def load_simulation_config(simulation_id: str) -> Optional[SimulationConfig]:
    """Load configuration for a specific simulation."""
    registry = get_simulations_registry()
    return registry.get_simulation(simulation_id)


def load_all_simulation_configs() -> List[SimulationConfig]:
    """Load all simulation configurations."""
    registry = get_simulations_registry()
    return registry.list_all_simulations()


def applicable_models_for_entity(
    entity_type: str,
    available_metrics: Set[str],
    category: Optional[str] = None,
) -> List[SimulationConfig]:
    """
    Get applicable simulation models for an entity.

    Args:
        entity_type: Type of entity
        available_metrics: Available metric names
        category: Optional category filter

    Returns:
        List of applicable simulation configurations
    """
    registry = get_simulations_registry()
    cat = SimulationCategory(category) if category else None
    return registry.get_applicable_simulations(entity_type, available_metrics, cat)

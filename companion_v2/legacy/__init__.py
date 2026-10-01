"""Declarative V1 compatibility inventory with no runtime access to V1."""

from .catalog import LEGACY_COMPATIBILITY_CATALOG, CatalogAction, LegacyCatalogEntry
from .scope_mapping import LegacyScopeMapping, LegacyScopeMappingDirectory
from .surface_ledger import (
    LEGACY_SURFACE_LEDGER,
    LegacySurfaceEntry,
    SurfaceClassification,
)
from .weather_migration import Difference, WeatherMigration, convert_weather_config

__all__ = [
    "CatalogAction",
    "Difference",
    "LEGACY_COMPATIBILITY_CATALOG",
    "LEGACY_SURFACE_LEDGER",
    "LegacyCatalogEntry",
    "LegacySurfaceEntry",
    "LegacyScopeMapping",
    "LegacyScopeMappingDirectory",
    "SurfaceClassification",
    "WeatherMigration",
    "convert_weather_config",
]

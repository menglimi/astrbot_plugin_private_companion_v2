"""Persistent optional capabilities and their voxel-room projections."""

from .models import (
    CapabilityAuthorization,
    CapabilityAuthorizationState,
    CapabilityDesiredState,
    CapabilityInstallation,
    CapabilityPackageDescriptor,
    CapabilityProjection,
    CapabilityRoleSelection,
    CapabilitySettings,
    FurnitureAvailability,
    FurnitureDescriptor,
    FurnitureProjection,
)
from .repositories import CapabilityRepository
from .management import CapabilityCommandReceipt, CapabilityManagementService

__all__ = [
    "CapabilityAuthorization",
    "CapabilityAuthorizationState",
    "CapabilityDesiredState",
    "CapabilityInstallation",
    "CapabilityPackageDescriptor",
    "CapabilityProjection",
    "CapabilityRepository",
    "CapabilityCommandReceipt",
    "CapabilityManagementService",
    "CapabilityRoleSelection",
    "CapabilitySettings",
    "FurnitureAvailability",
    "FurnitureDescriptor",
    "FurnitureProjection",
]

"""Locate PII as typed character spans on the source string."""

from edgepii._version import __version__
from edgepii.errors import DetectorLoadError, OverlapError, UnknownType
from edgepii.locator import Locator
from edgepii.quasi import Combination, find_combinations, has_combination
from edgepii.redact import redact
from edgepii.restore import RestoreResult, restore
from edgepii.span import LocateResult, Span
from edgepii.protection import (IncompleteDetectionError, ProtectionPlan, ProtectionSegment,
                                protection_plan, protect_mapping, redact_protected)
from edgepii.toolcall import (
    FieldHit,
    MaskedMapping,
    RestoredMapping,
    mask_mapping,
    restore_mapping,
)

__all__ = [
    "Combination",
    "DetectorLoadError",
    "FieldHit",
    "LocateResult",
    "Locator",
    "MaskedMapping",
    "OverlapError",
    "RestoreResult",
    "RestoredMapping",
    "Span",
    "IncompleteDetectionError",
    "ProtectionPlan",
    "ProtectionSegment",
    "protection_plan",
    "protect_mapping",
    "redact_protected",
    "UnknownType",
    "__version__",
    "find_combinations",
    "has_combination",
    "mask_mapping",
    "redact",
    "restore",
    "restore_mapping",
]

"""Locate PII as typed character spans on the source string."""

from edgepii._version import __version__
from edgepii.errors import DetectorLoadError, OverlapError, UnknownType
from edgepii.locator import Locator
from edgepii.redact import redact
from edgepii.restore import RestoreResult, restore
from edgepii.span import LocateResult, Span
from edgepii.toolcall import (
    FieldHit,
    MaskedMapping,
    RestoredMapping,
    mask_mapping,
    restore_mapping,
)

__all__ = [
    "DetectorLoadError",
    "FieldHit",
    "LocateResult",
    "Locator",
    "MaskedMapping",
    "OverlapError",
    "RestoreResult",
    "RestoredMapping",
    "Span",
    "UnknownType",
    "__version__",
    "mask_mapping",
    "redact",
    "restore",
    "restore_mapping",
]

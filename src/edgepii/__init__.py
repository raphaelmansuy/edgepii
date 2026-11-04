"""Locate PII as typed character spans on the source string."""

from edgepii._version import __version__
from edgepii.errors import DetectorLoadError, OverlapError, UnknownType
from edgepii.locator import Locator
from edgepii.redact import redact
from edgepii.span import LocateResult, Span

__all__ = [
    "DetectorLoadError",
    "LocateResult",
    "Locator",
    "OverlapError",
    "Span",
    "UnknownType",
    "__version__",
    "redact",
]

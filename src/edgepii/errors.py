"""Errors for the public locator. Messages do not include the source string."""


class UnknownType(ValueError):
    """The caller named a type that is not in the active taxonomy."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(name)


class DetectorLoadError(RuntimeError):
    """Weights or an extra failed to load. The message has no source text."""


class OverlapError(ValueError):
    """redact saw two spans that share a character."""

    def __init__(self, start: int, end: int) -> None:
        self.start = start
        self.end = end
        super().__init__(f"{start}:{end}")

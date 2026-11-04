"""ModelScope Siamese-UIE. A hit is public only when the slice equals the surface."""

from __future__ import annotations

from collections.abc import Callable

from edgepii.errors import DetectorLoadError
from edgepii.protocol import Hit


class UieDetector:
    max_chars = 2_000
    overlap_chars = 64

    def __init__(
        self,
        repo_id: str,
        revision: str,
        schema: dict[str, str],
        device: str = "cpu",
        runner: Callable | None = None,
    ) -> None:
        self.repo_id = repo_id
        self.revision = revision
        self.schema = schema
        self.device = device
        self._runner = runner
        if runner is not None:
            return
        try:
            from modelscope.pipelines import pipeline
            from modelscope.utils.constant import Tasks
        except ImportError as exc:
            raise DetectorLoadError(
                f"extra=ms repo={repo_id} revision={revision}"
            ) from exc
        try:
            self._pipe = pipeline(Tasks.siamese_uie, model=repo_id, model_revision=revision)
        except Exception as exc:
            raise DetectorLoadError(
                f"extra=ms repo={repo_id} revision={revision}"
            ) from exc

    def locate(self, source: str, labels: list[str]) -> tuple[Hit, ...]:
        if source == "":
            return ()
        allowed = {label.strip() for label in labels}
        schema = {
            name: None
            for name in self.schema.values()
            if name in allowed
        }
        if not schema:
            return ()
        if self._runner is not None:
            raw = self._runner(source, schema)
        else:
            raw = self._pipe(source, schema=schema)
        hits: list[Hit] = []
        for label, items in _pairs(raw):
            if not isinstance(items, list):
                continue
            for item in items:
                hit = _one(source, label, item, f"uie.{self.repo_id}")
                if hit is not None:
                    hits.append(hit)
        return tuple(hits)


def _pairs(raw: object) -> list[tuple[str, object]]:
    if isinstance(raw, dict) and "output" in raw and isinstance(raw["output"], dict):
        raw = raw["output"]
    if isinstance(raw, dict):
        return [(str(key), value) for key, value in raw.items()]
    return []


def _one(source: str, label: str, item: object, detector_id: str) -> Hit | None:
    if not isinstance(item, dict):
        return None
    surface = str(item.get("span") or item.get("text") or "")
    start, end = _bounds(item)
    if start is None or end is None or surface == "":
        return None
    if source[start:end] == surface:
        chosen = end
    elif end + 1 <= len(source) and source[start : end + 1] == surface:
        chosen = end + 1
    else:
        return None
    score = item.get("prob", item.get("probs", item.get("score")))
    return Hit(
        raw_label=str(item.get("type") or label),
        start=start,
        end=chosen,
        score=None if score is None else float(score),
        detector_id=detector_id,
    )


def _bounds(item: dict) -> tuple[int | None, int | None]:
    if "start" in item and "end" in item:
        return int(item["start"]), int(item["end"])
    offset = item.get("offset")
    if isinstance(offset, (list, tuple)) and len(offset) == 2:
        return int(offset[0]), int(offset[1])
    return None, None

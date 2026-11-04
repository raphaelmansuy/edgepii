"""GLiNER2 open-schema adapter. The type list is an input to the model."""

from __future__ import annotations

from edgepii.errors import DetectorLoadError
from edgepii.protocol import Hit


class Gliner2Detector:
    max_chars = 8_000
    overlap_chars = 64

    def __init__(
        self,
        repo_id: str,
        revision: str,
        device: str = "cpu",
        candidate_floor: float | None = None,
    ) -> None:
        self.repo_id = repo_id
        self.revision = revision
        self.device = device
        self.candidate_floor = candidate_floor
        try:
            from gliner2 import GLiNER2
        except ImportError as exc:
            raise DetectorLoadError(
                f"extra=gliner2 repo={repo_id} revision={revision}"
            ) from exc
        try:
            self._model = GLiNER2.from_pretrained(repo_id, revision=revision)
        except TypeError:
            self._model = GLiNER2.from_pretrained(repo_id)
        except Exception as exc:
            raise DetectorLoadError(
                f"extra=gliner2 repo={repo_id} revision={revision}"
            ) from exc

    def locate(self, source: str, labels: list[str]) -> tuple[Hit, ...]:
        if source == "" or not labels:
            return ()
        options: dict = {
            "include_confidence": True,
            "include_spans": True,
        }
        # The checkpoint author chose its own decision boundary. This adapter
        # adds no second one. A caller that measured a floor passes one.
        if self.candidate_floor is not None:
            options["threshold"] = self.candidate_floor
        result = self._model.extract_entities(source, labels, **options)
        return tuple(_hits_from_tree(result, f"gliner2.{self.repo_id}"))


def _hits_from_tree(node: object, detector_id: str, label: str | None = None) -> list[Hit]:
    hits: list[Hit] = []
    if isinstance(node, dict) and "start" in node and "end" in node:
        raw = str(node.get("label") or node.get("type") or label or "")
        score = node.get("confidence", node.get("score"))
        hits.append(
            Hit(
                raw_label=raw,
                start=int(node["start"]),
                end=int(node["end"]),
                score=None if score is None else float(score),
                detector_id=detector_id,
            )
        )
        return hits
    if isinstance(node, dict):
        for key, value in node.items():
            next_label = key if isinstance(key, str) else label
            hits.extend(_hits_from_tree(value, detector_id, next_label))
        return hits
    if isinstance(node, list):
        for item in node:
            hits.extend(_hits_from_tree(item, detector_id, label))
    return hits

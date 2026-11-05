"""GLiNER v1 adapter for nvidia/gliner-PII and the urchade PII checkpoint."""

from __future__ import annotations

from edgepii.errors import DetectorLoadError
from edgepii.protocol import Hit


class GlinerDetector:
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
            from gliner import GLiNER
        except ImportError as exc:
            raise DetectorLoadError(
                f"extra=gliner repo={repo_id} revision={revision}"
            ) from exc
        try:
            self._model = GLiNER.from_pretrained(repo_id, revision=revision)
            self._model.to(device)
            self._model.eval()
        except Exception as exc:
            raise DetectorLoadError(
                f"extra=gliner repo={repo_id} revision={revision}"
            ) from exc

    def locate(self, source: str, labels: list[str]) -> tuple[Hit, ...]:
        if source == "" or not labels:
            return ()
        options: dict = {}
        # The checkpoint sets its own boundary. Pass no second, unmeasured one.
        if self.candidate_floor is not None:
            options["threshold"] = self.candidate_floor
        rows = self._model.predict_entities(source, labels, **options)
        hits: list[Hit] = []
        for row in rows:
            hits.append(
                Hit(
                    raw_label=str(row.get("label") or ""),
                    start=int(row["start"]),
                    end=int(row["end"]),
                    score=None if row.get("score") is None else float(row["score"]),
                    detector_id=f"gliner.{self.repo_id}",
                    claimed_text=row.get("text"),
                )
            )
        return tuple(hits)

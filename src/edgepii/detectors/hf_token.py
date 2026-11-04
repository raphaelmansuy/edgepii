"""Hugging Face token classifiers. BERT and ModernBERT share this class."""

from __future__ import annotations

from edgepii.errors import DetectorLoadError
from edgepii.protocol import Hit


class HfTokenDetector:
    """A window is 75 percent of the checkpoint max position to stay under it."""

    default_context = 512
    context_fraction = 0.75
    overlap_chars = 64

    def __init__(self, repo_id: str, revision: str, device: str = "cpu") -> None:
        self.repo_id = repo_id
        self.revision = revision
        self.device = device
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise DetectorLoadError(
                f"extra=hf repo={repo_id} revision={revision}"
            ) from exc
        device_index = 0 if device == "cuda" else -1
        try:
            self._pipe = pipeline(
                "token-classification",
                model=repo_id,
                revision=revision,
                aggregation_strategy="simple",
                device=device_index,
            )
        except Exception as exc:
            raise DetectorLoadError(
                f"extra=hf repo={repo_id} revision={revision}"
            ) from exc
        self.max_chars = self._window_from_context()

    def _window_from_context(self) -> int:
        """Read the checkpoint limit. Characters here are a safe lower bound."""

        config = getattr(self._pipe.model, "config", None)
        positions = getattr(config, "max_position_embeddings", None)
        if not isinstance(positions, int) or positions <= 0:
            positions = self.default_context
        return max(1, int(positions * self.context_fraction))

    def locate(self, source: str, labels: list[str]) -> tuple[Hit, ...]:
        del labels
        if source == "":
            return ()
        rows = self._pipe(source)
        hits: list[Hit] = []
        for row in rows:
            start = int(row["start"])
            end = int(row["end"])
            raw = str(row.get("entity_group") or row.get("entity") or "")
            score = float(row["score"])
            hits.append(
                Hit(
                    raw_label=raw,
                    start=start,
                    end=end,
                    score=score,
                    detector_id=f"hf.{self.repo_id}",
                )
            )
        return tuple(hits)

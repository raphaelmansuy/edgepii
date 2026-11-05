"""Hugging Face token classifiers. BERT and ModernBERT share this class."""

from __future__ import annotations

from edgepii.errors import DetectorLoadError
from edgepii.protocol import Hit
from edgepii.windows import checked_windows


class HfTokenDetector:
    """Check tokenizer input lengths before every bounded model call."""

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
        try:
            self._pipe = pipeline(
                "token-classification",
                model=repo_id,
                revision=revision,
                aggregation_strategy="simple",
                device=device,
            )
        except Exception as exc:
            raise DetectorLoadError(
                f"extra=hf repo={repo_id} revision={revision}"
            ) from exc
        self.token_budget = self._window_from_context()
        self.max_chars = 1_000_000

    def _window_from_context(self) -> int:
        """Read the effective token limit, independent of source character count."""

        config = getattr(self._pipe.model, "config", None)
        positions = getattr(config, "max_position_embeddings", None)
        if not isinstance(positions, int) or positions <= 0:
            positions = self.default_context
        tokenizer_limit = getattr(getattr(self._pipe, "tokenizer", None), "model_max_length", positions)
        if isinstance(tokenizer_limit, int) and 0 < tokenizer_limit < positions:
            positions = tokenizer_limit
        return positions

    def locate(self, source: str, labels: list[str]) -> tuple[Hit, ...]:
        del labels
        if source == "":
            return ()
        hits: list[Hit] = []
        def count(text):
            return len(self._pipe.tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"])
        for offset, stop in checked_windows(source, count, self.token_budget, self.overlap_chars):
            for row in self._pipe(source[offset:stop]):
                hits.append(Hit(
                    raw_label=str(row.get("entity_group") or row.get("entity") or ""),
                    start=int(row["start"]) + offset,
                    end=int(row["end"]) + offset,
                    score=float(row["score"]),
                    detector_id=f"hf.{self.repo_id}",
                ))
        return tuple(hits)

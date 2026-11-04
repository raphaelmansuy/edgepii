"""Pinned preset rows. locate does not branch on the preset name."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Preset:
    name: str
    extra: str | None
    detectors: tuple[str, ...]
    repo_id: str | None
    revision: str


PRESETS: dict[str, Preset] = {
    "rules": Preset("rules", None, ("rules",), None, "rules"),
    "en-bert": Preset(
        "en-bert",
        "hf",
        ("rules", "hf_token"),
        "ab-ai/pii_model",
        "bbb5e83ef58a98f001e22c8315bc21d00e8064fd",
    ),
    "en-closed": Preset(
        "en-closed",
        "hf",
        ("rules", "hf_token"),
        "antoniogr7/pii-identifier-v0.1",
        "3d0f39eceaf0c95fc07943064c58fba3fff60243",
    ),
    "multi-open": Preset(
        "multi-open",
        "gliner2",
        ("rules", "gliner2"),
        "fastino/gliner2-privacy-filter-PII-multi",
        "1cb4166094dc58fa8d836429f060d6c95f62b495",
    ),
    "phi-open": Preset(
        "phi-open",
        "gliner",
        ("rules", "gliner"),
        "nvidia/gliner-PII",
        "bd23e8ef4425fd04e34c5204ab49ffaa706eae79",
    ),
    "zh-schema": Preset(
        "zh-schema",
        "ms",
        ("rules", "uie"),
        "iic/nlp_structbert_siamese-uie_chinese-base",
        # A tag, not the `master` branch. The repo publishes v1.0, v1.1, and
        # v1.2; a branch would let a rebuild change the weights under a fixed
        # version string. Design rule 8 says a preset pins a revision.
        "v1.2",
    ),
}

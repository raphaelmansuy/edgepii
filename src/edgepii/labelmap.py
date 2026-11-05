"""Load taxonomy 2026.11. This module is the only reader of the YAML file."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files

import yaml

from edgepii.errors import UnknownType


@dataclass(frozen=True, slots=True)
class TypeInfo:
    name: str
    class_name: str
    rank: int
    prefer: str
    redact: str


@dataclass(frozen=True, slots=True)
class Taxonomy:
    version: str
    types: dict[str, TypeInfo]
    labels: dict[str, str]
    schema_zh: dict[str, str]
    excluded_classes: tuple[str, ...]
    prompt_labels: dict[str, list[str]] = field(default_factory=dict)

    def public_type(self, raw_label: str) -> str | None:
        key = _norm(raw_label)
        found = self.labels.get(key)
        if found is not None:
            return found
        squashed = key.replace("_", "").replace("-", "")
        return self.labels.get(squashed)

    def raw_labels_for(self, type_names: list[str]) -> list[str]:
        wanted = set(type_names)
        labels = [raw for raw, public in self.labels.items() if public in wanted]
        labels.sort()
        return labels

    def default_types(self) -> list[str]:
        names = [
            info.name
            for info in self.types.values()
            if info.class_name not in self.excluded_classes
        ]
        names.sort()
        return names

    def prompt_labels_for(self, type_names: list[str], schema: str) -> list[str]:
        """Canonical model prompts, separate from output-label aliases."""
        wanted = set(type_names)
        return [label for label in self.prompt_labels[schema]
                if self.public_type(label) in wanted]

    def require(self, name: str) -> TypeInfo:
        info = self.types.get(name)
        if info is None:
            raise UnknownType(name)
        return info


def _norm(raw_label: str) -> str:
    key = raw_label.strip().casefold().replace(" ", "_")
    for prefix in ("b-", "i-", "l-", "u-", "e-", "s-"):
        if key.startswith(prefix):
            key = key[len(prefix) :]
            break
    return key


@lru_cache(maxsize=4)
def load_taxonomy(version: str = "2026.11") -> Taxonomy:
    if version != "2026.11":
        raise UnknownType(version)
    path = files("edgepii").joinpath("taxonomies/2026.11.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    classes = data["classes"]
    types: dict[str, TypeInfo] = {}
    for name, row in data["types"].items():
        class_name = row["class"]
        types[name] = TypeInfo(
            name=name,
            class_name=class_name,
            rank=int(classes[class_name]["rank"]),
            prefer=row["prefer"],
            redact=classes[class_name]["redact"],
        )
    labels = {_norm(raw): public for raw, public in data["labels"].items()}
    return Taxonomy(
        version=data["version"],
        types=types,
        labels=labels,
        schema_zh=dict(data["schema_zh"]),
        excluded_classes=tuple(data["default_excluded_classes"]),
        prompt_labels=dict(data.get("prompt_labels", {})),
    )

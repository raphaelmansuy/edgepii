"""Mask the string values inside a structured argument tree.

An agent sends data as a tool call: a mapping of field names to values, nested
to any depth. Three things go wrong when such a call is treated as one string.

1. A detector reads the serialised text, so its offsets land on bracket and
   quote characters rather than on the value. A caller cannot mask by field.
2. An encoder escapes a character, so ``ada\\u0040example.com`` holds no ``@``
   and every address rule misses it.
3. A mask that rewrites the whole call can break the structure that the tool
   needs to parse.

This module walks the tree, scans each **string leaf after decoding it**, and
replaces the leaf with a masked string. Field paths record what changed, so a
journal can say "customer.email was masked" without copying the value.

The two directions are separate, because a redaction policy usually treats them
differently: masking an outbound argument is always safe, while masking an
inbound result can break a workflow that needs the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from edgepii.redact import redact
from edgepii.restore import restore
from edgepii.span import Span


@dataclass(frozen=True, slots=True)
class FieldHit:
    """One string leaf that a detector matched.

    `path` is a dotted field path such as `args.customer.email`. `types` lists
    the public types found in that leaf. Neither field holds the original value.
    """

    path: str
    types: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"path": self.path, "types": list(self.types)}


@dataclass(frozen=True, slots=True)
class MaskedMapping:
    """A masked copy of the input, the vault, and the field journal."""

    value: object
    vault: dict[str, str] = field(default_factory=dict)
    hits: tuple[FieldHit, ...] = ()
    dropped: int = 0
    unmapped: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.hits)

    def to_dict(self) -> dict:
        """Export the journal. `value` holds the masked tree, never the original."""

        return {
            "value": self.value,
            "hits": [hit.to_dict() for hit in self.hits],
            "dropped": self.dropped,
            "unmapped": self.unmapped,
            "changed": self.changed,
        }


@dataclass(frozen=True, slots=True)
class RestoredMapping:
    """A restored copy of an inbound tree, plus what could not be resolved."""

    value: object
    resolved: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    unknown: tuple[Span, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.unresolved and not self.unknown


def _scope(token: str, index: int) -> str:
    """Give a placeholder a tree-unique name: <EMAIL_1> becomes <EMAIL_1_1>.

    The second number is the leaf counter, not the field name, because a field
    name can hold characters a placeholder should not. It keeps the token shape
    that `restore` matches.
    """

    if not token.startswith("<") or not token.endswith(">"):
        return token
    inner = token[1:-1]
    return f"<{inner}_{index}>"


def mask_mapping(
    value,
    locator,
    *,
    types: list[str] | None = None,
) -> MaskedMapping:
    """Return a copy of `value` with every detected string leaf masked.

    The input is never modified. A string leaf becomes the masked string, so the
    structure a tool parses is unchanged. A non-string leaf is copied as is.

    `locator` is a `Locator`, and `types` narrows the scan the same way
    `locate` does. This is the outbound half: call it on the arguments before the
    call leaves the host.
    """

    hits: list[FieldHit] = []
    vault: dict[str, str] = {}
    dropped = 0
    unmapped = 0

    def walk(node, path: str):
        nonlocal dropped, unmapped
        if isinstance(node, str):
            result = locator.locate(node, types=types)
            dropped += result.dropped
            unmapped += getattr(result, "unmapped", 0)
            if not result.spans:
                return node
            masked, local = redact(node, result.spans)
            # `redact` numbers each type from 1 within one string, so two leaves
            # would both produce `<EMAIL_1>`. Restoring would then write the
            # first value into both fields and lose the second. Prefix the token
            # with the field index so every placeholder in the tree is unique.
            for token, original in local.items():
                scoped = _scope(token, len(vault))
                masked = masked.replace(token, scoped)
                vault[scoped] = original
            hits.append(FieldHit(path=path, types=tuple(sorted({s.type for s in result.spans}))))
            return masked
        if isinstance(node, dict):
            return {
                key: walk(item, f"{path}.{key}" if path else str(key))
                for key, item in node.items()
            }
        if isinstance(node, (list, tuple)):
            items = [
                walk(item, f"{path}[{index}]" if path else f"[{index}]")
                for index, item in enumerate(node)
            ]
            return items if isinstance(node, list) else tuple(items)
        return node

    masked_value = walk(value, "")
    return MaskedMapping(value=masked_value, vault=vault, hits=tuple(hits), dropped=dropped, unmapped=unmapped)


def restore_mapping(
    value,
    vault: dict[str, str],
    *,
    locator=None,
    types: list[str] | None = None,
) -> RestoredMapping:
    """Return a copy of an inbound tree with every placeholder resolved.

    This is the inbound half. Use it on the arguments the model produced and on
    the arguments it sends to a tool. A placeholder that the model invented is
    reported in `unresolved`, never silently left in the tree.
    """

    resolved: list[str] = []
    unresolved: list[str] = []
    unknown: list[Span] = []

    def walk(node):
        if isinstance(node, str):
            result = restore(node, vault, locator=locator, types=types)
            for token in result.resolved:
                if token not in resolved:
                    resolved.append(token)
            for token in result.unresolved:
                if token not in unresolved:
                    unresolved.append(token)
            unknown.extend(result.unknown)
            return result.text
        if isinstance(node, dict):
            return {key: walk(item) for key, item in node.items()}
        if isinstance(node, (list, tuple)):
            items = [walk(item) for item in node]
            return items if isinstance(node, list) else tuple(items)
        return node

    restored_value = walk(value)
    return RestoredMapping(
        value=restored_value,
        resolved=tuple(resolved),
        unresolved=tuple(unresolved),
        unknown=tuple(unknown),
    )

# ADR 0006: Protect candidate coverage independently of typed selection

Status: implemented as an opt-in API, 5 November 2026.

Typed conflict resolution removed candidate protection for two high-severity
legal spans and one medical span in the measured public prefixes. Keep typed
entity description separate from protection of the source characters.

Add `ProtectionPlan`, `Locator.plan`, `protection_plan`, `redact_protected`, and
`protect_mapping` alongside the existing typed APIs. Union overlapping eligible
candidates into neutral protection components with type/detector provenance.
Adjacent components stay separate; no heterogeneous public PII type is invented.

If any candidate in an overlap component is irreversible, make the whole
component irreversible. This conservative choice prevents credential fragments
entering the vault but can also make non-secret text non-restorable. Propagate
exact known-secret repetitions, including across mapping leaves. Repetition
matching is policy, never a repair of invalid detector offsets.

Bind plans to the exact source. Validate all supplied ranges/surfaces, avoid
placeholder collisions, and export neither source values nor the binding hash
from `to_dict`. Strict mode rejects dropped/unmapped diagnostics; it does not
certify PII recall. Explicit tuple-path field policies protect whole string
values without relying on a detector cue. Missing/non-string policy targets
fail. Mapping keys and scalar types are preserved.

Keep this policy opt-in until negative damage and restoration costs meet
deployment criteria. Sorting, provenance aggregation, and literal repetition
scanning all contribute cost; no production latency bound is claimed.

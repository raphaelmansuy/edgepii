# ADR 0002. Two default lanes

<!-- ste: descriptive -->

Status: accepted as a candidate policy. Date: 4 November 2026. Promotion to a measured default waits on the sealed freeze. See [evaluation](../09-evaluation.md).

## Context

A closed token classifier is enough when the type list and the domain stay fixed. An open-schema model is enough when the caller must change types per call. One checkpoint cannot be optimal for both facts. Card F1 values disagree between papers, so they cannot choose the winner. See the [research landscape](../04-research-landscape.md).

## Decision

V1 wires two candidate presets, plus a BERT control and a rule preset.

| Preset | Checkpoint | Lane |
| --- | --- | --- |
| `en-closed` | `antoniogr7/pii-identifier-v0.1` | ModernBERT token classifier |
| `multi-open` | `fastino/gliner2-privacy-filter-PII-multi` | GLiNER2, types at call time |
| `en-bert` | `ab-ai/pii_model` | BERT-base control |
| `rules` | none | Checksums and shapes |

The team escalates from `en-closed` to `multi-open` in two cases. The type list must move, or the dev freeze shows a miss the encoder does not close. The team does not start on the heavier model by default.

`phi-open` (`nvidia/gliner-PII`) stays unwired until the taxonomy includes health types and the team accepts the license.

## Options rejected

| Option | Why the team rejected it |
| --- | --- |
| BERT-base as the only model | Context and the 2024 encoder train are weaker. It remains the control |
| GLiNER2 as the only model | Closed English calls would pay for open schema they do not use |
| The highest paper F1 as the default | The tables disagree, and the test is not our freeze |
| A custom train in v1 | Measure the public checkpoints first |

## Consequences

Two adapters share `Hit`, the label map, and the merger. Preset rows differ. `locate` does not branch on the preset name. If the sealed freeze shows `en-bert` matching `en-closed` inside the latency budget, the team can demote ModernBERT. That change is a new ADR, not a silent edit.

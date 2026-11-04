# ADR 0003. Local weights in v1

<!-- ste: descriptive -->

Status: accepted. Date: 4 November 2026.

## Context

A local step masks the text before any remote model sees it. The parent note requires that order. A detector that sends the source string to a cloud PII API makes a copy before the mask exists. That copy breaks fact F6 in the [first principles](../02-first-principles.md).

## Decision

V1 detectors load weights on the host, or they use local rules. Hugging Face and ModelScope are download hubs for weights, not runtime APIs for the source string. The download runs when the caller constructs the preset, from the pinned revision.

Cloud detect products stay out of the preset list. A future bridge can exist for a host that is already inside the vendor boundary. That bridge needs a new ADR. It is not a default.

## Options rejected

| Option | Why the team rejected it |
| --- | --- |
| Amazon Comprehend, Azure Language PII, or Google Sensitive Data Protection as the engine | The source string leaves the host |
| A chat model on a vendor API that returns JSON spans | Same copy. Also a judge problem if code does not check the spans |
| "Local" mode that falls back to a cloud call on error | The failure path would leak |

## Consequences

Install extras pull `transformers`, `gliner2`, `gliner`, or `modelscope`. Tests for rules and merge do not need those extras. `DetectorLoadError` names the missing extra and does not send the source string anywhere.

Latency budgets are CPU-first until a deployment note says otherwise. See principle 6 in [AI engineering](../03-ai-engineering.md).

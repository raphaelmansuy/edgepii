# ADR 0005: Resolve direct conflicts without discarding disjoint spans

Status: accepted for implementation, 5 November 2026.

The previous merger selected one winner from each transitively connected
overlap component. A losing broad span could connect two disjoint identifiers
and cause one to disappear. Injected `PERSON[0:20]`, `GOV_ID[5:9]`, and
`EMAIL[18:30]` reproduced this defect: only the government-ID span survived.

Resolve candidates in the existing deterministic priority order. Accept a
candidate when it conflicts with no already accepted span. Reject only direct
conflicts, then continue. Keep severity, lane preference, length, score, start,
and type ordering. Add detector/label tie-breakers to make equal candidates
stable across input permutation.

Use compressed interval coordinates and prefix-sum indexes to check conflicts
in logarithmic time. The complete operation is O(n log n), including sorting;
do not replace the old sweep with a quadratic all-pairs comparison.

The output remains a disjoint typed span list on the original source. This
decision does not claim every rejected candidate is harmless, does not invent
a type for a heterogeneous union, and does not establish complete PII recall.
Evaluate actual character containment separately from typed exact match.

Acceptance: the bridge case keeps both disjoint winners; nested-secret,
adjacency, duplicate, permutation, and large-chain tests pass. Record this
behavioral change in the changelog and preserve old evaluation reports.

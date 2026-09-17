# Overfull pilot v0 incident

## Summary

The `flowguard_stress` server pilot intentionally exceeded the fixed tile's
placement capacity. Global placement stopped with `GPL-0301` at 109.884%
effective utilization; all 24 matrix records were retained as
`CRASH/NO_METRICS` rather than treated as missing data.

## Classification

This is a deterministic `PLACEMENT_FAIL`, not a synthesis, timing, routing,
PDK, or infrastructure failure. The pinned environment is LibreLane 3.0.14
with Sky130. The incident record is
`experiments/incidents/pilot_overfull_v0.json`.

## Recovery and guardrails

The pilot is evidence for failure-aware acquisition. Re-run only with a new
trial namespace and preserved status provenance. Configuration preflight must
allow `GPL_CELL_PADDING`, reject legacy `CELL_PAD`, and protect clock/RTL/PDK
and fixed-tile inputs. Do not silently resize the tile or modify RTL to make
this pilot feasible.

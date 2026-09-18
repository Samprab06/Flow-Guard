# Crossbar v2 comparison

This is an audited sequential replay over deterministic physical characterization outcomes; no comparison call launched LibreLane.
Each cache row is rebuilt through `src.parser.build_record` from its metrics/status/config files. The manifest records runner status, missing metrics, setup/hold, routing completion/overflow, DRC, LVS, and signoff checks.
Frozen RTL, footprint, clock, and knob bounds are recorded in `frozen_manifest.json`.

| Method | Budget | Feasible | First feasible call | Best QoR |
|---|---:|---:|---:|---:|
| default | 6 | 3 | 4 | 0.3112996180098017 |
| vanilla_bo | 6 | 3 | 3 | 0.3112996180098017 |
| flowguard_raw | 6 | 3 | 3 | 0.3112996180098017 |

The default policy is a fixed no-model order after the shared failing initialization; Vanilla BO and FlowGuard use the existing drivers unchanged.
All methods receive two shared initialization outcomes and four adaptive selections. Infeasible outcomes carry no QoR.
Conclusion: this small replay demonstrates the frozen mixed boundary and equal-budget policy behavior, but is not evidence of general optimizer superiority.

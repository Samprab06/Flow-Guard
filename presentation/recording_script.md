# FlowGuard — four-minute recording script

## 0:00–0:25 — Purpose
FlowGuard asks whether feasibility-aware search can spend less EDA time on failed configurations, while holding the crossbar, constraints, and evaluation budget fixed.

## 0:25–0:50 — Boundary
The authoritative crossbar-v2 oracle has 36 configurations: six feasible and thirty failed at fixed 19.9 nanoseconds. This replaces the older stress benchmark; stress evidence is excluded.

## 0:50–1:15 — Model
Quality and feasibility stay separate. Expected improvement is multiplied by predicted feasibility. The experiment compares Vanilla, FlowGuard, and EI-only under matched initialization and equal 24-evaluation budgets.

## 1:15–1:45 — Demo decision and artifact
The traceable demo is seed 11, FlowGuard-Calibrated, adaptive call 10: cb36_002. It is rank one of 27 candidates, with EI zero and probability of feasibility 0.08. The result is feasible, with QoR minus 0.093068, positive setup and hold slack, DRC zero, routing 100, and LVS/signoff pass. The cb36_002 PNG is authentic, but comes from a separate earlier banked physical run; replay launched zero physical runs. The exact SHA is shown on slide 4.

## 1:45–2:05 — Frozen protocol
The protocol is crossbar-v2 at 19.9 nanoseconds: 36 configurations, 13 seeds, three methods, and 24 evaluations per method—eight shared initialization evaluations plus sixteen adaptive evaluations. There is no replay EDA.

## 2:05–2:45 — Main result + demo
The headline is: feasibility weighting reduced failed-run compute by 4.1 percent. FlowGuard versus matched EI-only search across 13 replay seeds. The editable zero-based chart shows 249.91 minutes for EI-only and 239.63 for FlowGuard.

**Demo:** click the chart and open its data table. The 10.28-minute difference is derived from verified failed means: 14,994.8 minus 14,378.0 seconds, divided by 60. The 4.11 percent is that 616.8-second difference divided by the EI-only mean. All final QoR values tie, and FlowGuard matches EI-only on best-call across all 13 seeds. Total EDA cost is slightly higher for FlowGuard than Vanilla and EI-only.

## 2:45–3:15 — Support comparison
Vanilla has the lowest failed EDA mean, 13,046.8 seconds, and the lowest total EDA mean, 17,230.7 seconds. FlowGuard is 14,378.0 failed and 17,307.3 total; EI-only is 14,994.8 failed and 17,272.8 total. All three tie final QoR.

## 3:15–3:40 — Reproducibility and limitations
An older TPE layout image is a physical artifact, not a FlowGuard decision record. The crossbar replay is an oracle/cache process with banked physical outcomes. There is no standalone combined-13 verification log. Seed 47 is shared-init luck, and the result does not establish general optimizer superiority.

## 3:40–4:00 — Invitation
Run `python3 experiments/replay_demo.py`, inspect cb36_002, and independently verify the separate physical artifact chain. Then test a new design or seed set with a standalone combined verification log.

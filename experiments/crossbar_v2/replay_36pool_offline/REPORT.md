# Offline sequential replay over the committed 36-point physical oracle

Label: `OFFLINE-SEQUENTIAL-REPLAY-36POOL` (not a live campaign; no optimizer
or EDA runs were launched).

## Predeclared setup

* Oracle (sole data source): `experiments/crossbar_v2/char36_results_ledger.json`
  (36 entries, 6 feasible, 2 distinct feasible QoR values; oracle-best QoR
  `-0.093068237` at `cb36_002` / `cb36_006` / `cb36_010`, which are knob-
  duplicate arms with identical physical metrics).
* Seeds: 11, 29, 47 (exact). Budget per method: 8 shared init + 16 adaptive
  = 24 total. Pool order `cb36_000..cb36_035`; ties break to pool order.
* Shared init IDs per seed (drawn once via
  `numpy.random.default_rng(seed).choice(36, 8, replace=False)`, drawn order,
  identical across methods within a seed):
  * seed 11: `cb36_001, cb36_034, cb36_003, cb36_020, cb36_019, cb36_024,
    cb36_029, cb36_015` (first feasible at call 1)
  * seed 29: `cb36_018, cb36_009, cb36_016, cb36_001, cb36_022, cb36_017,
    cb36_027, cb36_007` (first feasible at call 2)
  * seed 47: `cb36_014, cb36_015, cb36_003, cb36_024, cb36_022, cb36_016,
    cb36_004, cb36_002` (first feasible at call 8; oracle-best arm in init)
* Methods:
  * `vanilla_bo_penalty` — `src.primary_loop.VanillaBODriver`: GP on all
    observed (infeasible mapped to `INFEASIBLE_PENALTY=1.0`), plain EI,
    `p_feas=1.0`, no calibration.
  * `flowguard_calibrated` — `src.primary_loop.FlowGuardCalibratedDriver`:
    feasible-only QoR GP, score = EI x P(feasible) from RF; RF calibrates
    (sigmoid, cv=3) only with >=3 samples per class, else uncalibrated
    fallback; no hard risk threshold.
  * `ei_only_ablation` — same feasible-only QoR GP preprocessing/fitting
    (`scale_features` / `fit_qor_gp`) and EI acquisition
    (`expected_improvement`) as FlowGuard, but `p_feas` fixed to 1.0 and no
    feasibility classifier of any kind.
* Driver GP randomness: driver seed = replay seed, matched across methods.
  `FeasibilityModel` randomness is frozen internally (`random_state=0`).
* Identical fallback until first feasible: while zero feasible observed, ALL
  methods pick argmax P(feasible) from a freshly fitted
  `src.models.FeasibilityModel` (ties to pool order). This overrides
  Vanilla's native penalty-GP ranking in the pre-feasible regime so the
  comparison isolates post-feasible acquisition. (Not triggered in these
  traces: every per-seed init already contained a feasible arm; the code
  path is implemented and asserted, fallback_uses=0 everywhere.)
* Hiding: each trace reveals ledger outcomes only for IDs it selects
  (`HiddenOracle`); unselected outcomes are never accessed. No-replacement
  enforced (216 unique selections audited: 9 traces x 24).
* No-feasible +inf handling: best feasible QoR recorded as null with
  `best_qor_inf=true` (+inf semantics: worse than any feasible score).
  Not triggered here (all 9 traces feasible); curves emit empty cells
  until the first feasible call.
* Guardrails: no LibreLane/EDA launch, no RTL edits, no primary-file edits.
  Script imports only stdlib + numpy/sklearn/scipy + `src.primary_loop` /
  `src.models`. Static self-check asserts no launch/compute-surface imports.
  `/proc` snapshots before/after: 0 EDA-named processes both times
  (see `verification.log`). Nothing committed.

## Per-seed x method table (primary endpoint: final best feasible QoR)

| seed | method | best feasible QoR | first feas call | best-QoR call | feas / infeas | failed EDA rt (s) | total EDA rt (s) | optimizer overhead (s) | replay wall (s) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 11 | vanilla_bo_penalty | -0.093068237 | 1 | 15 | 6 / 18 | 13322.465 | 17506.364 | 0.1223 | 0.1233 |
| 11 | flowguard_calibrated | -0.093068237 | 1 | 10 | 5 / 19 | 13778.944 | 17179.807 | 3.0217 | 3.0229 |
| 11 | ei_only_ablation | -0.093068237 | 1 | 10 | 3 / 21 | 15126.522 | 17126.880 | 0.1302 | 0.1312 |
| 29 | vanilla_bo_penalty | -0.093068237 | 2 | 15 | 6 / 18 | 13547.325 | 17731.225 | 0.1239 | 0.1248 |
| 29 | flowguard_calibrated | -0.093068237 | 2 | 10 | 5 / 19 | 14134.972 | 17535.835 | 3.2654 | 3.2666 |
| 29 | ei_only_ablation | -0.093068237 | 2 | 10 | 5 / 19 | 14350.847 | 17751.710 | 0.1446 | 0.1458 |
| 47 | vanilla_bo_penalty | -0.093068237 | 8 | 8 | 6 / 18 | 12640.407 | 16824.306 | 0.1286 | 0.1296 |
| 47 | flowguard_calibrated | -0.093068237 | 8 | 8 | 5 / 19 | 14155.128 | 17555.991 | 2.8947 | 2.8960 |
| 47 | ei_only_ablation | -0.093068237 | 8 | 8 | 3 / 21 | 15502.705 | 17503.063 | 0.1277 | 0.1288 |

(machine-readable: `per_seed_method_table.csv`; full per-call records with
provenance in `replay_36pool_offline_results.json`.)

## Win counts and secondary summaries

* Per-seed winners (lowest final best feasible QoR; exact ties share the win):
  seed 11, 29, 47 each a 3-way tie. Win counts: vanilla 3, FlowGuard 3,
  EI-only 3. **No method wins outright on the primary endpoint.**
* Mean / median across seeds per method:
  * mean best QoR: -0.093068237 for all three (median identical).
  * mean feasible count: vanilla 6.0, FlowGuard 5.0, EI-only 3.67
    (medians 6.0 / 5.0 / 3.0).
  * mean first-feasible call: 3.67 for all (init-driven, identical inits).
  * mean failed EDA runtime: vanilla 13170.1 s, FlowGuard 14023.0 s,
    EI-only 14993.4 s (medians 13322.5 / 14135.0 / 15126.5 s).
  * mean total empirical EDA runtime: vanilla 17354.0 s, FlowGuard
    17423.9 s, EI-only 17460.6 s (all within ~1%).
  * mean optimizer overhead (24 calls): vanilla 0.12 s, EI-only 0.13 s,
    FlowGuard 3.06 s (RF + calibration refits; negligible vs EDA hours).

## Curves vs evaluations (best feasible QoR; `inf` = none yet)

Full trajectories in `curves_best_qor_vs_evals.csv`. Checkpoints:

| seed | method | call 8 | call 12 | call 16 | call 20 | call 24 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 11 | vanilla | 0.3113 | 0.3113 | -0.0931 | -0.0931 | -0.0931 |
| 11 | flowguard | 0.3113 | -0.0931 | -0.0931 | -0.0931 | -0.0931 |
| 11 | ei-only | 0.3113 | -0.0931 | -0.0931 | -0.0931 | -0.0931 |
| 29 | vanilla | 0.3113 | 0.3113 | -0.0931 | -0.0931 | -0.0931 |
| 29 | flowguard | 0.3113 | -0.0931 | -0.0931 | -0.0931 | -0.0931 |
| 29 | ei-only | 0.3113 | -0.0931 | -0.0931 | -0.0931 | -0.0931 |
| 47 | all three | -0.0931 | -0.0931 | -0.0931 | -0.0931 | -0.0931 |

On seeds 11/29 FlowGuard and EI-only reach oracle-best at call 10 (2nd
adaptive pick, `cb36_002` in both); Vanilla needs until call 15 (7th
adaptive pick). On seed 47 the best arm sits in the shared init, so all
curves coincide from call 8 (init luck, not policy).

## Curves vs cumulative empirical EDA compute (best QoR @ compute)

| seed | method | @call 8 | @call 12 | @call 16 | @call 24 |
| ---: | --- | ---: | ---: | ---: | ---: |
| 11 | vanilla | 0.3113 @ 5170 s | 0.3113 @ 7971 s | -0.0931 @ 10464 s | -0.0931 @ 17506 s |
| 11 | flowguard | 0.3113 @ 5170 s | -0.0931 @ 8552 s | -0.0931 @ 11659 s | -0.0931 @ 17180 s |
| 11 | ei-only | 0.3113 @ 5170 s | -0.0931 @ 8367 s | -0.0931 @ 12216 s | -0.0931 @ 17127 s |
| 29 | vanilla | 0.3113 @ 6877 s | 0.3113 @ 9458 s | -0.0931 @ 12919 s | -0.0931 @ 17731 s |
| 29 | flowguard | 0.3113 @ 6877 s | -0.0931 @ 10074 s | -0.0931 @ 12430 s | -0.0931 @ 17536 s |
| 29 | ei-only | 0.3113 @ 6877 s | -0.0931 @ 10074 s | -0.0931 @ 12578 s | -0.0931 @ 17752 s |
| 47 | all three | -0.0931 @ 6715 s | -0.0931 @ ~9143-10091 s | -0.0931 @ ~12085-12624 s | -0.0931 @ 16824-17556 s |

(Cumulative compute = running sum of committed ledger `runtime_s` over
selected arms only; full per-call series in `curves_best_qor_vs_evals.csv`.)

## Failed-compute comparison

Failed EDA runtime = sum of committed `runtime_s` over selected infeasible
arms (wasted empirical compute); counts in parentheses:

| seed | vanilla | flowguard | ei-only |
| ---: | ---: | ---: | ---: |
| 11 | 13322 s (18) | 13779 s (19) | 15127 s (21) |
| 29 | 13547 s (18) | 14135 s (19) | 14351 s (19) |
| 47 | 12640 s (18) | 14155 s (19) | 15503 s (21) |
| mean | 13170 s | 14023 s | 14993 s |

Vanilla wastes the least failed compute and collects the most feasible arms
(6/6/6: it re-samples the duplicated feasible patterns `cb36_005`,
`cb36_009` early, then `006/010/002`); EI-only spends the most picks in
infeasible AREA 1/2 space (only 3 feasible on seeds 11/47). The feasibility
gate steers toward the best arm faster but does not reduce total failed
picks here — the gate's probability mass is diffuse (selected `p_feas`
mostly 0.1-0.6, calibration active from call ~12 once >=3 samples per class
accumulate).

## Adaptive selections (for audit)

* seed 11 vanilla: `005, 000, 013, 009, 021, 011, 006, 010, 018, 002, 035,
  008, 014, 022, 027, 032`
* seed 11 flowguard: `000, 002, 009, 014, 006, 030, 026, 018, 022, 010, 032,
  035, 028, 031, 027, 023`
* seed 11 ei-only: `000, 002, 006, 018, 014, 030, 026, 022, 032, 035, 023,
  028, 031, 011, 008, 027`
* seed 29 vanilla: `005, 000, 008, 035, 024, 032, 002, 014, 006, 010, 025,
  033, 003, 011, 013, 021`
* seed 29 flowguard: `000, 002, 014, 006, 030, 026, 034, 010, 032, 035, 024,
  028, 031, 023, 015, 020`
* seed 29 ei-only: `000, 002, 014, 006, 026, 030, 034, 024, 031, 028, 035,
  032, 010, 012, 015, 020`
* seed 47 vanilla: `006, 010, 011, 033, 001, 013, 005, 009, 035, 032, 021,
  008, 000, 030, 027, 029`
* seed 47 flowguard: `000, 001, 009, 006, 026, 030, 034, 018, 010, 035, 032,
  031, 027, 028, 023, 020`
* seed 47 ei-only: `000, 001, 006, 018, 030, 026, 034, 032, 035, 020, 023,
  028, 031, 011, 008, 027`

(`cb36_` prefixes omitted; full IDs in results JSON.)

## Final physical metrics of each trace's best pick

All 9 traces terminate at QoR -0.093068237 arms (`002`/`006`/`010`
pattern: `GPL_CELL_PADDING=2, GRT_ADJUSTMENT=0.2, SYNTH_STRATEGY=AREA 0`),
whose committed physical metrics are identical: area 37314.5 um2,
wirelength 141422 um, critical delay 19.7091 ns, setup_ws +0.1909 ns,
hold_ws +0.1337 ns, DRC 0, LVS pass, signoff pass. Best-pick IDs:
seed 11: vanilla `cb36_006` (call 15), flowguard `cb36_002` (call 10),
ei-only `cb36_002` (call 10); seed 29: vanilla `cb36_002` (call 15),
flowguard `cb36_002` (call 10), ei-only `cb36_002` (call 10); seed 47: all
`cb36_002` (call 8, shared init).

## Honest conclusion

* On the predeclared primary endpoint — final best feasible QoR under equal
  24-call budgets — this replay is a **3-way tie on every seed**: all
  methods reach the oracle-best arm within budget. It provides **no evidence
  of general optimizer superiority** for any method.
* Secondary signals split and are hypothesis-generating only:
  feasibility-aware / feasible-only EI (FlowGuard and the EI-only ablation)
  reach the best arm 5 calls earlier than Vanilla penalty BO on 2 of 3
  seeds; Vanilla collects more feasible arms overall and wastes ~7-14% less
  failed EDA compute. Optimizer overhead differs by ~25x in relative terms
  (0.12 s vs 3.1 s total) but is negligible against ~4.7-4.9 h of empirical
  EDA compute per trace.
* Limitations that prevent stronger claims: the oracle holds only 6
  feasible arms with 2 distinct QoR values (3 best arms are knob-duplicates
  with identical metrics), so the task is near-saturated; seed 47 is
  decided by init luck (best arm in shared init); n=3 seeds; the shared
  pre-feasible fallback was never exercised (all inits feasible); GP fits
  emit sklearn `ConvergenceWarning`s (constant-kernel bound, frozen primary
  behavior, unchanged); and an offline replay over a fixed 36-point pool
  cannot measure exploration value outside the pool.
* What would strengthen the comparison: a larger pool with a denser
  feasible set and distinct QoR spread, seeds whose inits exclude the best
  arm, and reporting time-to-best and failed-compute as co-primary with
  final QoR.

## Files (all under experiments/crossbar_v2)

* `replay_36pool_offline.py` — replay script (this report's method).
* `replay_36pool_offline/replay_36pool_offline_results.json` — 9 traces x 24
  calls with outcomes, provenance, and summaries.
* `replay_36pool_offline/per_seed_method_table.csv` — the table above.
* `replay_36pool_offline/curves_best_qor_vs_evals.csv` — per-call best-QoR
  and cumulative empirical compute / overhead series.
* `replay_36pool_offline/verification.log` — /proc snapshots (0 EDA
  processes before/after), static-guard notes, data source.
* `replay_36pool_offline/REPORT.md` — this file.

Reproduce: `.venv/ml/bin/python experiments/crossbar_v2/replay_36pool_offline.py`
from the repo root. No EDA, no network, no commits.

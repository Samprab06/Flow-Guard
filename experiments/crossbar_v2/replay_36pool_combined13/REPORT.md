# Combined 13-seed cached replay over the frozen 36-point measured oracle

Labels: `OFFLINE-SEQUENTIAL-REPLAY-36POOL` (legacy seeds 11, 29, 47) +
`OFFLINE-SEQUENTIAL-REPLAY-36POOL-EXT10` (extension seeds 101, 103, 107,
109, 113, 127, 131, 137, 139, 149) merged verbatim as
`OFFLINE-SEQUENTIAL-REPLAY-36POOL-COMBINED13`. Cached replay only: no
EDA/LibreLane launches, no optimizer runs outside the replay, no RTL or
primary-file edits. Nothing committed.

## Frozen protocol (identical for all 13 seeds)

* Oracle (sole data source):
  `experiments/crossbar_v2/char36_results_ledger.json` (36 entries,
  6 feasible, 2 distinct feasible QoR values; oracle-best QoR
  `-0.093068237` at `cb36_002` / `cb36_006` / `cb36_010`, knob-duplicate
  arms with identical physical metrics).
* Benchmark/methods/budget/init/models exactly as committed in
  `experiments/crossbar_v2/replay_36pool_offline.py`:
  8 shared init + 16 adaptive = 24 per method; shared init per seed drawn
  once via `numpy.random.default_rng(seed).choice(36, 8, replace=False)`
  in drawn order, identical across the three methods within a seed;
  driver seed = replay seed matched across methods;
  `FeasibilityModel` randomness frozen (`random_state=0`); ties break to
  pool order via `numpy.argmax`.
* Methods: `vanilla_bo_penalty` (`VanillaBODriver`, GP on all observed
  with `INFEASIBLE_PENALTY=1.0`, plain EI, `p_feas=1.0`),
  `flowguard_calibrated` (`FlowGuardCalibratedDriver`, feasible-only QoR
  GP, EI x P(feasible) from RF with sigmoid calibration iff >=3 samples
  per class else uncalibrated fallback), `ei_only_ablation` (same
  feasible-only QoR GP preprocessing/fitting and EI as FlowGuard, but
  `p_feas=1.0` and no feasibility classifier of any kind).
* Identical pre-feasible fallback: while zero feasible observed, ALL
  methods select argmax P(feasible) from a freshly fitted
  `src.models.FeasibilityModel` (ties to pool order). Overrides Vanilla's
  native penalty-GP ranking pre-feasible so the comparison isolates
  post-feasible acquisition.
* Hiding: `HiddenOracle` reveal-on-select per trace; unselected outcomes
  never accessed; no-replacement enforced (39 traces x 24 = 936 unique
  audited selections per trace; 216 legacy + 720 extension).
* Extension seeds were exactly predeclared before results: 101, 103, 107,
  109, 113, 127, 131, 137, 139, 149. Legacy seeds 11, 29, 47 kept
  separate (rerun never; traces copied verbatim from
  `replay_36pool_offline_results.json` with only backfilled
  `cum_*_to_best` summaries derived from their own committed per-call
  records).
* Guardrails: script imports only stdlib + numpy/sklearn/scipy +
  `src.primary_loop` / `src.models` (static self-check passed);
  `/proc` snapshots 0 EDA-named processes before and after (see ext10
  `verification.log` and JSON `ps_before`/`ps_after`); GP
  `ConvergenceWarning`s are frozen-primary behavior, unchanged.

## Per-seed x method table (primary endpoint: final best feasible QoR)

Machine-readable: `per_seed_method_table.csv` (adds `cum_eda_s_to_best`,
`cum_total_eda_s_to_best`, `cum_failed_eda_s_to_best` = cumulative
empirical EDA seconds at the best-QoR call). Columns also include best
QoR vs evaluation (via `curves_best_qor_vs_evals.csv`), cumulative
empirical EDA seconds to best candidate, failed-run EDA seconds, total
empirical EDA seconds, first feasible call, best call, feasible /
infeasible counts, optimizer overhead, replay wall time, fallback uses.

| seed | method | best QoR | first feas | best call | feas/infeas | failed EDA (s) | total EDA (s) | cum EDA to best (s) | overhead (s) | wall (s) | fallback |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 11 | vanilla | -0.093068237 | 1 | 15 | 6/18 | 13322.465 | 17506.364 | 9852.439 | 0.1223 | 0.1233 | 0 |
| 11 | flowguard | -0.093068237 | 1 | 10 | 5/19 | 13778.944 | 17179.807 | 6425.066 | 3.0217 | 3.0229 | 0 |
| 11 | ei-only | -0.093068237 | 1 | 10 | 3/21 | 15126.522 | 17126.880 | 6425.066 | 0.1302 | 0.1312 | 0 |
| 29 | vanilla | -0.093068237 | 2 | 15 | 6/18 | 13547.325 | 17731.225 | 11581.348 | 0.1239 | 0.1248 | 0 |
| 29 | flowguard | -0.093068237 | 2 | 10 | 5/19 | 14134.972 | 17535.835 | 10073.887 | 3.2654 | 3.2666 | 0 |
| 29 | ei-only | -0.093068237 | 2 | 10 | 5/19 | 14350.847 | 17751.710 | 10073.887 | 0.1446 | 0.1458 | 0 |
| 47 | vanilla | -0.093068237 | 8 | 8 | 6/18 | 12640.407 | 16824.306 | 6715.219 | 0.1286 | 0.1296 | 0 |
| 47 | flowguard | -0.093068237 | 8 | 8 | 5/19 | 14155.128 | 17555.991 | 6715.219 | 2.8947 | 2.8960 | 0 |
| 47 | ei-only | -0.093068237 | 8 | 8 | 3/21 | 15502.705 | 17503.063 | 6715.219 | 0.1277 | 0.1288 | 0 |
| 101 | vanilla | -0.093068237 | 10 | 16 | 6/18 | 12715.025 | 16898.925 | 11195.276 | 0.1145 | 0.1155 | 2 |
| 101 | flowguard | -0.093068237 | 10 | 11 | 4/20 | 14610.852 | 17223.085 | 7069.500 | 2.6241 | 2.6252 | 2 |
| 101 | ei-only | -0.093068237 | 10 | 11 | 3/21 | 15187.815 | 17188.173 | 7069.500 | 0.1666 | 0.1718 | 2 |
| 103 | vanilla | -0.093068237 | 1 | 1 | 6/18 | 13520.570 | 17704.469 | 607.801 | 0.1455 | 0.1466 | 0 |
| 103 | flowguard | -0.093068237 | 1 | 1 | 4/20 | 14723.850 | 17336.331 | 607.801 | 3.6271 | 3.6283 | 0 |
| 103 | ei-only | -0.093068237 | 1 | 1 | 3/21 | 15258.903 | 17259.509 | 607.801 | 0.1884 | 0.1896 | 0 |
| 107 | vanilla | -0.093068237 | 2 | 2 | 6/18 | 12560.201 | 16744.100 | 1242.980 | 0.1351 | 0.1361 | 0 |
| 107 | flowguard | -0.093068237 | 2 | 2 | 5/19 | 13892.367 | 17293.230 | 1242.980 | 3.4210 | 3.4222 | 0 |
| 107 | ei-only | -0.093068237 | 2 | 2 | 3/21 | 14995.437 | 16999.869 | 1242.980 | 0.1228 | 0.1239 | 0 |
| 109 | vanilla | -0.093068237 | 2 | 2 | 6/18 | 12747.511 | 16931.410 | 1129.558 | 0.1269 | 0.1279 | 0 |
| 109 | flowguard | -0.093068237 | 2 | 2 | 4/20 | 14671.075 | 17283.308 | 1129.558 | 2.7397 | 2.7409 | 0 |
| 109 | ei-only | -0.093068237 | 2 | 2 | 3/21 | 15186.224 | 17190.656 | 1129.558 | 0.1249 | 0.1259 | 0 |
| 113 | vanilla | -0.093068237 | 3 | 3 | 6/18 | 12647.270 | 16831.170 | 1662.713 | 0.1196 | 0.1206 | 0 |
| 113 | flowguard | -0.093068237 | 3 | 3 | 4/20 | 14372.524 | 16984.757 | 1662.713 | 2.8101 | 2.8113 | 0 |
| 113 | ei-only | -0.093068237 | 3 | 3 | 3/21 | 15124.897 | 17125.255 | 1662.713 | 0.1229 | 0.1240 | 0 |
| 127 | vanilla | -0.093068237 | 1 | 4 | 6/18 | 13606.792 | 17790.691 | 3312.663 | 0.1787 | 0.1800 | 0 |
| 127 | flowguard | -0.093068237 | 1 | 4 | 4/20 | 14819.307 | 17431.540 | 3312.663 | 4.2192 | 4.2205 | 0 |
| 127 | ei-only | -0.093068237 | 1 | 4 | 3/21 | 15160.918 | 17165.350 | 3312.663 | 0.2219 | 0.2231 | 0 |
| 131 | vanilla | -0.093068237 | 3 | 17 | 6/18 | 13118.517 | 17302.416 | 11877.606 | 0.3092 | 0.3103 | 0 |
| 131 | flowguard | -0.093068237 | 3 | 11 | 5/19 | 13720.792 | 17300.517 | 7905.243 | 3.8769 | 3.8780 | 0 |
| 131 | ei-only | -0.093068237 | 3 | 11 | 5/19 | 13945.003 | 17524.727 | 7905.243 | 0.3273 | 0.3285 | 0 |
| 137 | vanilla | -0.093068237 | 2 | 2 | 6/18 | 12793.528 | 16977.428 | 1949.370 | 0.2957 | 0.2968 | 0 |
| 137 | flowguard | -0.093068237 | 2 | 2 | 4/20 | 14429.854 | 17042.087 | 1949.370 | 3.4911 | 3.4923 | 0 |
| 137 | ei-only | -0.093068237 | 2 | 2 | 3/21 | 15131.152 | 17135.584 | 1949.370 | 0.1314 | 0.1325 | 0 |
| 139 | vanilla | -0.093068237 | 7 | 7 | 6/18 | 13647.509 | 17831.408 | 5187.074 | 0.1249 | 0.1260 | 0 |
| 139 | flowguard | -0.093068237 | 7 | 7 | 4/20 | 14720.873 | 17333.106 | 5187.074 | 2.7690 | 2.7702 | 0 |
| 139 | ei-only | -0.093068237 | 7 | 7 | 3/21 | 15366.291 | 17366.649 | 5187.074 | 0.1286 | 0.1297 | 0 |
| 149 | vanilla | -0.093068237 | 3 | 3 | 6/18 | 12740.888 | 16924.787 | 1849.774 | 0.1325 | 0.1336 | 0 |
| 149 | flowguard | -0.093068237 | 3 | 3 | 4/20 | 14883.275 | 17495.509 | 1849.774 | 2.8329 | 2.8341 | 0 |
| 149 | ei-only | -0.093068237 | 3 | 3 | 4/20 | 14596.099 | 17208.332 | 1849.774 | 0.1700 | 0.1712 | 0 |

(All cells from `per_seed_method_table.csv`, which governs.)

Shared init IDs (drawn order; oracle-best arms 002/006/010 bold):

* 101: 028, 008, 026, 011, 035, 013, 021, 004 (no feasible; fallback x2)
* 103: **002**, **006**, 007, 030, 016, 009, 018, 023 (best at call 1)
* 107: 017, **010**, 019, 026, 003, 028, 015, 027 (best at call 2)
* 109: 029, **010**, 007, 026, 025, 011, 013, 016 (best at call 2)
* 113: 023, 033, **002**, 021, 025, 008, 004, 014 (best at call 3)
* 127: 001, 014, 013, **006**, 035, 032, 018, **010** (best at call 4)
* 131: 032, 031, 005, 019, 021, 018, 013, 009 (no oracle-best; adaptive)
* 137: 022, **006**, 025, 014, 033, 007, 008, 027 (best at call 2)
* 139: 029, 018, 023, 004, 012, 020, **002**, 013 (best at call 7)
* 149: 007, 025, **002**, 026, 008, 030, 031, 020 (best at call 3)

## Curves

* `curves_best_qor_vs_evals.csv`: per seed x method x call (1..24):
  best feasible QoR so far (empty until first feasible),
  `cum_failed_eda_runtime_s`, `cum_total_eda_runtime_s`,
  `cum_optimizer_overhead_s`. Cumulative empirical EDA seconds to the
  best candidate = `cum_total_eda_runtime_s` at `best_qor_call`
  (tabulated above as `cum EDA to best`).
* Only 4 of 13 seeds require adaptive discovery of the best arm (11, 29,
  101, 131). On all four, FlowGuard and EI-only reach oracle-best at the
  same call (10, 10, 11, 11) while Vanilla needs calls 15, 15, 16, 17.
  The other 9 seeds are decided inside the shared init (best call <= 8,
  identical across methods by construction).

## FlowGuard vs EI-only: feasibility-weighting ablation (explicit)

* FlowGuard-Calibrated and the EI-only ablation share the identical
  feasible-only QoR GP preprocessing/fitting (`scale_features` /
  `fit_qor_gp`) and EI acquisition (`expected_improvement`). Their ONLY
  difference is the feasibility gate: FlowGuard multiplies EI by
  P(feasible) from the RF classifier; EI-only fixes `p_feas=1.0` with no
  classifier of any kind.
* Result on all 13 seeds: FlowGuard best-QoR call == EI-only best-QoR
  call on every seed (10/10, 10/10, 8/8, 11/11, 1/1, 2/2, 2/2, 3/3, 4/4,
  11/11, 2/2, 7/7, 3/3). The feasibility weight changes NEITHER the
  final best QoR (13/13 ties) NOR the time-to-best on any seed.
* Therefore the faster discovery shared by FlowGuard AND EI-only over
  Vanilla penalty BO on seeds 11, 29, 101, 131 must NOT be attributed to
  feasibility weighting. It is attributable to what the two share
  against Vanilla: the feasible-only QoR GP + plain EI ranking (vs
  Vanilla's penalty-mapped GP on all observed with INFEASIBLE_PENALTY).
  The feasibility gate's marginal contribution in this pool is zero on
  both endpoints; its only visible 13-seed signal is a secondary
  feasible-count difference (mean feasible arms: FlowGuard 4.38 vs
  EI-only 3.38; Vanilla 6.0) at higher failed compute than Vanilla
  (mean failed EDA s: Vanilla 13046.8, FlowGuard 14378.0, EI-only
  14994.8) with total EDA within ~0.5% (means 17230.7 / 17307.3 /
  17272.8 s) and negligible overhead (means 0.16 / 3.20 / 0.16 s).

## Win counts and secondary summaries (13 seeds)

* Per-seed winners (lowest final best feasible QoR; exact ties share):
  all 13 seeds 3-way ties. Win counts: vanilla 13, FlowGuard 13,
  EI-only 13. No method wins outright on the primary endpoint.
* Mean best QoR: -0.093068237 for all three (median identical).
* Mean feasible count: vanilla 6.0, FlowGuard 4.38, EI-only 3.38
  (medians 6.0 / 4.0 / 3.0).
* Mean first-feasible call: 3.46 for all (init-driven, identical inits).
* Mean failed EDA runtime: vanilla 13046.8 s, FlowGuard 14378.0 s,
  EI-only 14994.8 s.
* Mean total empirical EDA runtime: vanilla 17230.7 s, FlowGuard
  17307.3 s, EI-only 17272.8 s.
* Mean optimizer overhead (24 calls): vanilla 0.16 s, EI-only 0.16 s,
  FlowGuard 3.20 s (RF + calibration refits; negligible vs EDA hours).
* Shared pre-feasible fallback exercised only on seed 101
  (`fallback_uses=2` for all three methods, calls 9-10); all other
  inits already contained a feasible arm.

## Honest conclusion

* On the predeclared primary endpoint (final best feasible QoR, equal
  24-call budgets), the 13-seed replay is a 3-way tie on every seed: no
  evidence of general optimizer superiority for any method.
* The feasibility-weighting ablation is null: FlowGuard-Calibrated never
  beats or loses to EI-only on final QoR or time-to-best across 13
  seeds. The discovery-speed gap vs Vanilla on 4 seeds belongs to the
  shared feasible-only EI component, not to feasibility weighting, and
  must be reported that way.
* Limitations: oracle holds only 6 feasible arms with 2 distinct QoR
  values (3 best arms knob-duplicates); 9/13 seeds decided by init luck;
  n=13 still small; offline replay over a fixed 36-point pool cannot
  measure exploration outside the pool.

## Files

* `../replay_36pool_ext10/replay_36pool_ext10_results.json` — 30
  extension traces x 24 calls (outcomes, provenance, summaries).
* `../replay_36pool_ext10/per_seed_method_table.csv` — extension table.
* `../replay_36pool_ext10/curves_best_qor_vs_evals.csv` — extension
  curves.
* `../replay_36pool_ext10/verification.log` — /proc snapshots (0 EDA
  before/after), static-guard notes, data source.
* `replay_36pool_combined13_results.json` — 39 combined traces
  (9 legacy verbatim + 30 extension) with per-call records.
* `per_seed_method_table.csv` — combined 13-seed table (this report).
* `curves_best_qor_vs_evals.csv` — combined 13-seed curves.
* `REPORT.md` — this file.

Reproduce: `.venv/ml/bin/python
experiments/crossbar_v2/replay_36pool_ext10.py` from the repo root. No
EDA, no network, no commits. Legacy results are read, never rerun.

# FlowGuard Handoff TODO

This is the active implementation queue for `experiment/server-runs`. Checked
items are evidence-backed. Do not mark a campaign phase complete from a process
exit code alone; require final metrics and preserved artifacts.

## Immediate Server Recovery

- [x] Pull recovery benchmark commit `9aea48a` or newer on the Oracle server.
- [ ] Run `./scripts/openlane-setup.sh` and capture the pinned runtime output.
- [ ] Validate that the 2x1 horizontal-abutment geometry is legal in the
      TinyTapeout integration environment.
- [x] Run namespace `pilot_repaired_tile_v3` with the 20 ns fixed clock.
- [x] Confirm all 27 trials create complete final metrics.
- [ ] If safe probes fail, stop and record a new incident; do not consume the
      full pilot budget.
- [ ] Preserve `results/pilot_repaired_tile_v3/manifest.csv`, status log,
      aggregates, effective configs, and representative raw reports.
- [x] Reparse v3 raw metrics with the corrected parser and archive complete
      hold/routing/LVS/signoff evidence; do not reuse old feasible labels.
- [ ] Run three identical repeats for at least three configurations to quantify
      physical metric noise before boundary selection.
- [x] Run `experiments/v3_analysis.py` against the server aggregate JSONL and
      preserve its machine-readable report.
- [x] Confirm v3 is one feasibility class and therefore not optimizer-ready.
- [ ] Characterize fixed clocks at 17, 15, 13, and 11 ns before changing the
      search-space or optimizer policy.

## Completed Foundation

- [x] Pin LibreLane, container digest, Python lock, Sky130 revision, and PDK.
- [x] Verify counter baseline through all 80 LibreLane stages.
- [x] Implement fixed CSD FIR and verify 428-cell synthesis/full flow.
- [x] Implement stress MAC and measure 728 cells/109.884% placement failure.
- [x] Implement runner, parser, feasibility model, QoR model, and acquisition.
- [x] Add immutable experiment namespaces and raw-run ignore rules.
- [x] Archive `pilot_overfull_v0` as invalid optimizer evidence.
- [x] Add strict LibreLane config preflight.
- [x] Add runtime provenance and `GPL-0301` placement classification.
- [x] Add 2x1 manifest/launcher and ChipIgnite top-three scaffolding.
- [x] Add parser failure-stage aggregation regression coverage.

## Recovery Launcher Gaps

- [ ] Make staged gates explicit: safe 3 must produce a valid final-metrics
      result before middle 8; middle must pass before aggressive 16.
- [ ] Make failed preflight trials produce a structured result without creating
      misleading missing-directory errors.
- [ ] Add a preflight-only mode that validates all candidate overlays without
      launching EDA.
- [ ] Add process-group timeout cleanup and orphan-process checks.
- [ ] Add resume repair for trials with status files but parser failures while
      preserving immutable original records.
- [ ] Propagate the declared seed into runner/model metadata and record it in
      every effective config.
- [ ] Return nonzero for failed gates and distinguish infrastructure failure
      from candidate-caused EDA failure.

## Metrics and Feasibility

- [ ] Parse setup WNS/TNS and hold WNS/TNS from structured STA reports.
- [ ] Parse routing completion, overflow, wirelength, and route DRC metrics.
- [ ] Parse Magic/KLayout DRC and LVS reports with source paths.
- [ ] Add failure precedence: precheck, synthesis, placement, CTS, timing,
      routing, DRC, LVS, timeout, tool crash, missing metrics.
- [ ] Implement canonical feasible-only objective:
      `0.50 critical delay + 0.25 routed wirelength + 0.25 cell area` after
      nonzero baseline normalization.
- [ ] Reject missing denominators, mixed units, incomplete timing, and missing
      objective metrics.
- [x] Add complete metric fixtures and strict incomplete-record feasibility
      behavior on `experiment/recovery-benchmark`.
- [ ] Add fixtures for safe success, GPL-0301, timing failure, routing failure,
      DRC failure, timeout, malformed reports, and missing metrics.

## Experiment Contract

- [ ] Freeze the repaired design, 2x1 allocation, 20 ns clock, PDK, flow,
      objective, four knobs, bounds, seeds, timeout, and concurrency in a
      versioned manifest.
- [ ] Resolve the current knob policy: `FP_CORE_UTIL`,
      `PL_TARGET_DENSITY_PCT`, `GPL_CELL_PADDING`, `GRT_ADJUSTMENT`, and
      `SYNTH_STRATEGY` currently expose five controls; the final benchmark must
      freeze exactly four as required by the directive.
- [ ] Generate one deterministic Sobol candidate pool with seed/hash and reuse
      it for random, vanilla BO, FlowGuard-Raw, and FlowGuard-Calibrated.
- [ ] Register eight shared initialization candidates before optimizer traces.
- [ ] Enforce the staged 3/8/16 pilot separately from the final 24-call traces.
- [ ] Preserve failed calls in the canonical trial ledger.
- [x] Add a versioned diagnostic-boundary manifest for the fixed 20 ns pilot.

## Online Optimization

- [ ] Connect history -> model update -> acquisition -> runner -> parser ->
      append record -> next candidate.
- [ ] Refactor GP to a declared Matérn kernel with normalized inputs/target,
      fixed seed, jitter, and persisted hyperparameters.
- [ ] Train RF feasibility on all attempts and calibrate only after declared
      class/sample thresholds.
- [ ] Implement FlowGuard-Raw and FlowGuard-Calibrated policy variants.
- [ ] Record model ID, training-data hash, feature schema, seed, prediction
      mean/std, feasibility probability, EI, acquisition score, rank, and
      selected candidate.
- [ ] Add deterministic synthetic boundary, one-class, no-feasible, leakage,
      and repeatability tests.
- [ ] Add Random, Vanilla BO, and Optuna TPE baselines with equal budgets and
      fixed seeds.

## Storage and Resume

- [ ] Add canonical append-only `trials.jsonl`.
- [ ] Add append-only `selections.jsonl` and `stage_predictions.jsonl`.
- [ ] Add manifest snapshot, CSV/Parquet exports, and integrity report.
- [ ] Implement `PLANNED -> SELECTED -> DISPATCHED -> RUNNING -> FINALIZING
      -> COMPLETED` state transitions.
- [ ] Validate unique trial IDs, call indices, candidate IDs, config hashes,
      source/flow/clock matches, units, and budget before each model update.
- [ ] Stop only the affected trace on integrity failure; never train through
      corrupted history.

## Stage-Aware Shadow Predictor

- [ ] Capture SYNTHESIS, PLACEMENT, CTS, and GLOBAL_ROUTE snapshots.
- [ ] Preserve null/missing/not-run distinctions.
- [ ] Train a versioned RF shadow predictor after every 8-16 completed runs.
- [ ] Use grouped or leave-one-run-out evaluation by trial.
- [ ] Do not early-stop primary runs.
- [ ] Report hypothetical CPU-hours saved, recall, precision, and false-abort
      rate only after the primary dataset is frozen.

## Exact Campaign Budgets

- [ ] Pilot: 16 unique trials, excluded from final scores unless manifest says
      otherwise.
- [ ] Primary: 8 shared initialization plus 16 calls each for Random, TPE,
      Vanilla BO, FlowGuard-Raw, and FlowGuard-Calibrated: 88 total.
- [ ] Held-out design: 8 shared initialization plus 16 Vanilla BO and 16
      calibrated FlowGuard: 40 total.
- [ ] Fresh validation reruns: 6.
- [ ] Grand total: 150 physical-design calls.
- [ ] Keep debug/smoke jobs in separate namespaces and budgets.

## ChipIgnite / Open-MPW Track

- [x] Add authoritative catalog source metadata.
- [x] Add offline inventory, scoring, and migration-report scaffolding.
- [ ] Run catalog mining with Internet access and pin repository commit SHAs.
- [ ] License-audit and rank UETRV_ESoC_v2, binoy01/chipignite, and
      dineshannayya/mbist_ctrl.
- [ ] Clone only candidates that pass digital/SKY130/RTL/license screening.
- [ ] Preserve original configs, migrated LibreLane configs, unsupported-key
      reports, and manual interventions.
- [ ] Produce at least three modern baseline candidates before FlowGuard case
      studies.
- [ ] Keep historical GDS as provenance only; compare modern baseline versus
      modern FlowGuard for causal claims.
- [ ] Add deterministic same-scale KLayout rendering outside this data-only
      branch if visual artifacts are needed.

## Final Validation

- [ ] Freshly rerun each headline winner from clean source/config.
- [ ] Compare stored versus fresh metrics and record agreement/difference.
- [ ] Run integrity audit and config-diff audit.
- [ ] Verify no raw runs are committed to Git.
- [ ] Export raw tables and archive representative success/failure reports.
- [ ] Do not start dashboard/triage work until the primary controlled
      experiment and fresh validation pass.

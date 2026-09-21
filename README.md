# FlowGuard

Failure-aware physical-design autotuning for LibreLane/OpenROAD and Sky130.

FlowGuard asks one question: **under the same number of RTL-to-GDS evaluations,
does explicitly learning physical-design feasibility reach a high-quality valid
implementation with fewer wasted EDA runs than conventional search?**

The answer under test is an acquisition that multiplies Expected Improvement by
the probability of feasibility (`EI x P(feasible)`), with a Gaussian Process
trained on feasible trials only and a Random Forest trained on every attempt.

## Status (2026-09-20)

The completed primary study is the frozen crossbar-v2 measured-oracle replay.
It compares Vanilla penalty BO, FlowGuard-Calibrated, and matched EI-only over
13 seeds. Replay launches no physical EDA; it attaches recorded outcomes from
36 previously measured SKY130/LibreLane configurations.

**Frozen evidence: `experiments/crossbar_v2/final_evidence_bundle/`**

| Setting | Value |
|---|---|
| Clock | **19.9 ns** (fixed; never an optimizer variable) |
| Knobs | `GPL_CELL_PADDING {0,2}`, `SYNTH_STRATEGY {AREA 0,1,2}`, `PL_TARGET_DENSITY_PCT {38,45,52}`, `GRT_ADJUSTMENT {0.05,0.10,0.15,0.20}` |
| Fixed | Crossbar RTL, die area 320x200 um, `FP_CORE_UTIL 30`, pinned environment |
| Oracle | 36 measured configurations: 6 feasible, 30 infeasible |
| Budget | 8 shared init + 16 adaptive per method |
| Objective | `qor_v1_crossbar_v2` = 0.5 critical delay + 0.3 wirelength + 0.2 cell area |
| Flow | LibreLane 3.0.14, sky130A rev `8afc8346...`, pinned container digest |

**Completed 13-seed comparison (means; lower cost is better):**

| Method | Failed EDA seconds | Total EDA seconds | Final QoR |
|---|---|---|---|
| Vanilla penalty BO | 13,046.8 | 17,230.7 | -0.093068237 |
| FlowGuard-Calibrated | 14,378.0 | 17,307.3 | -0.093068237 |
| EI-only | 14,994.8 | 17,272.8 | -0.093068237 |

All methods tie final QoR for every seed. FlowGuard and EI-only reach their best
candidate at identical evaluations for every seed. FlowGuard's failed-runtime
mean is 4.11% lower than EI-only's, with slightly higher total runtime; Vanilla
has the lowest recorded failed and total evaluation costs.

## Repository layout

| Path | Contents |
|---|---|
| `flowguard/runner/` | deterministic single-trial LibreLane runner |
| `flowguard/metrics/parser.py` | evidence parsing and feasibility gate |
| `flowguard/models/` | feasibility Random Forest and feasible-only QoR GP |
| `flowguard/optimizers/` | optimizer drivers and decision provenance |
| `flowguard/scripts/` | setup, physical-run, and campaign launchers |
| `flowguard/designs/` | bundled FIR and stress designs |
| `flowguard/tests/` | parser, model, optimizer, and replay regressions |
| `experiments/crossbar_v2/final_evidence_bundle/` | frozen crossbar study evidence |

## Environment setup

The baseline pins LibreLane `3.0.14`, all Python dependency hashes, the
Linux/amd64 container digest, and the compatible Sky130 PDK revision. The
dependency lock targets Python 3.12. On Ubuntu with Docker available:

```bash
bash flowguard/scripts/openlane-setup.sh
bash flowguard/scripts/openlane-smoke.sh
bash flowguard/scripts/openlane-run.sh
bash flowguard/scripts/openlane-run.sh flowguard_fir
```

`openlane-setup.sh` creates an ignored virtual environment, downloads the
pinned LibreLane container and PDK, and executes the smoke flow.
`openlane-run.sh` runs a bundled design and writes ignored artifacts under
`designs/<design>/runs/`.

## Running experiments

All launchers are resumable, refuse to overwrite raw evidence, and write
append-only JSONL ledgers. Use a new namespace whenever a manifest, config, or
parser changes.

```bash
# Fixed-clock boundary hunt (never launches an optimizer)
bash flowguard/scripts/launch_clock_hunt.sh --namespace <namespace> \
  --hunt flowguard/experiments/manifests/clock_hunt_15p8ns_v1.json --hours 5

# One primary optimizer method over the frozen pool
bash flowguard/scripts/launch_primary_v1.sh --method flowguard_raw \
  --shared-from primary-init-v1 --budget 24 --hours 5
```

Methods: `random`, `optuna_tpe`, `vanilla_bo`, `flowguard_raw`,
`flowguard_calibrated`.

## Results and evidence

Raw LibreLane output is intentionally not tracked in Git. Each namespace under
`results/<namespace>/` contains:

- `manifest.jsonl` / `trials.jsonl` — immutable canonical ledgers
- `summary.json`, `status.json`, `status.log` — live progress
- `configs/<trial-id>/config.json` — effective, hashed configs
- `runs/trial_<trial-id>/` — `status.json`, runner logs, `final/` (metrics, GDS,
  netlist, timing/DRC/LVS reports), `final/render/*.png` (KLayout layout images)

Infrastructure failures (`NO_METRICS`, timeouts, killed launchers) are kept
separate from physical-design failures and never treated as configuration
labels. `scripts/prune_fail_steps.sh` reclaims bulky intermediate step
directories from timing-fail trials while retaining all audit evidence.

## Models, objective, and feasibility

- Feasibility: `RandomForestClassifier(n_estimators=50, random_state=0)`, split
  first, then silently falls back to constant probability for one-class data.
  Calibration activates only when each class has at least three samples.
- QoR: Gaussian Process on feasible trials only
  (`ConstantKernel * RBF`, `alpha=1e-6`, `normalize_y=True`), constant fallback
  for a single sample.
- Acquisition: `EI x P(feasible)` with no hard risk threshold. Vanilla BO uses
  a predeclared infeasible penalty of 1.0 on the normalized scale.
- Feasibility gate: successful flow, DRC 0, worst setup slack >= 0, worst hold
  slack >= 0, routing complete with zero overflow, LVS and signoff pass, no
  missing metrics. Worst slack (not violation-only WNS) decides timing.
- Every FlowGuard selection stores 17 provenance fields (training IDs and hash,
  model versions, calibration state, predicted mean/variance/feasibility, EI,
  acquisition score, rank, selected candidate).

## Tests

```bash
python3 -m unittest discover -s flowguard/tests
```

The model/acquisition and primary-loop tests require numpy, scikit-learn,
scipy, and optuna (see `flowguard/requirements.txt`).

## Related work

`flowguard/chipignite/` is a data-only scaffold for screening external SKY130/Open-MPW
designs; the catalog tooling is offline and no external design has been
hardened by this project yet.

## Assumptions and limitations

- The primary result is an offline replay over a measured 36-point oracle, not
  a new physical campaign or live-search wall-time measurement.
- Recorded EDA `runtime_s` sums estimate sequential evaluation cost; optimizer
  overhead is reported separately.
- No standalone combined-13 verification log exists; the combined result keeps
  before/after zero-process snapshots.
- The deck's `cb36_002` PNG is authentic but comes from a separate banked
  characterization run linked by candidate ID.

## Archived replay demo

The smallest offline demo is an **archived measured-evidence replay**. It
re-reads the committed decision and measurement in
`experiments/crossbar_v2/final_evidence_bundle/06_demo.json`, checks the frozen settings and
provenance, and prints the recorded result:

```bash
python3 experiments/replay_demo.py
```

Prerequisite: Python 3.12+; the replay itself uses only the standard library.
It was smoke-tested with Python 3.13.14. Expected output includes
`REPLAY: ... physical EDA processes launched: 0`, the source/bundle revisions,
the frozen 19.9 ns setting, selected `cb36_002`, and a final
`FRESH EDA: not run` line. The raw measured fields and optimizer provenance
are in `experiments/crossbar_v2/final_evidence_bundle/06_demo.json`; the
bundle manifest, 39 method-by-seed rows, 936 traces, aggregates, parser audit,
and validation are beside it. `06_demo.json` links seed 11, call 10, and
`cb36_002`; its layout is from the separately preserved characterization run,
not replay. These are evidence sources, not new measurements.

The exact verification commands used for this deliverable were:

```bash
python3 experiments/replay_demo.py
python3 -m unittest flowguard.tests.test_replay_demo flowguard.tests.test_parser
python3 -m unittest discover -s flowguard/tests
```

The replay passed, replay plus parser regressions passed 13 tests, and the full
suite passed 38 tests after installing the declared `optuna>=3.0` dependency
into the existing user environment. This was not a clean-environment install.

This command does not run synthesis, placement, routing, STA, DRC, LVS,
signoff, or an optimizer. It cannot establish that the current checkout still
passes: the record belongs to its stated source revision and frozen design,
constraints, libraries, and tool versions. Cost figures are sums of recorded
EDA `runtime_s` values, not replay wall time. The combined 13-seed result has
before/after zero-process snapshots but no standalone combined verification
log. For a fresh physical check, use the
actual repository scripts, for example:

```bash
bash flowguard/scripts/openlane-smoke.sh
bash flowguard/scripts/openlane-run.sh flowguard_fir
```

Those commands require Docker, the pinned LibreLane/PDK setup, and substantially
more time; they are separate from replay. If replay reports missing evidence,
run it from the repository root and verify that
`experiments/crossbar_v2/final_evidence_bundle/06_demo.json` is present. If a fresh run cannot find
Docker or the pinned environment, install the prerequisites and run
`bash flowguard/scripts/openlane-setup.sh` first.

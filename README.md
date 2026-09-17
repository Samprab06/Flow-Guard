# FlowGuard

Failure-aware physical-design autotuning for LibreLane/OpenROAD and Sky130.

FlowGuard asks one question: **under the same number of RTL-to-GDS evaluations,
does explicitly learning physical-design feasibility reach a high-quality valid
implementation with fewer wasted EDA runs than conventional search?**

The answer under test is an acquisition that multiplies Expected Improvement by
the probability of feasibility (`EI x P(feasible)`), with a Gaussian Process
trained on feasible trials only and a Random Forest trained on every attempt.

## Status (2026-09-17)

The project has a frozen, validated benchmark and a running five-method
comparison on real SKY130/LibreLane runs. The design under test is the dense
sensor MAC `tt_um_flowguard_stress` (728 synthesized cells) on an assumed 2x1
TinyTapeout tile (320x100 um).

**Frozen benchmark: `experiments/manifests/primary_benchmark_v1.json`**

| Setting | Value |
|---|---|
| Clock | **15.8 ns** (fixed; never an optimizer variable) |
| Knobs | `GPL_CELL_PADDING {0,2}`, `SYNTH_STRATEGY {AREA 0,1,2}`, `PL_TARGET_DENSITY_PCT {38,45,52}`, `GRT_ADJUSTMENT {0.05,0.10,0.15,0.20}` |
| Fixed | `FP_CORE_UTIL 30` (measured to have zero effect) |
| Pool | 72 candidates, seed 0, sha256 `6c41874c...` (`experiments/pools/pool_15p8_v1.json`) |
| Budget | 8 shared init + 16 adaptive per method |
| Objective | `qor_v1` = 0.5 critical delay + 0.3 wirelength + 0.2 cell area (`experiments/objective_qor_v1.json`) |
| Flow | LibreLane 3.0.14, sky130A rev `8afc8346...`, pinned container digest |

**Feasibility boundary characterization:** 17 ns broadly passes (310/325
feasible, worst setup slack 0.86-1.92 ns); 15 ns broadly fails (0/160 feasible,
all setup timing failures); 16.0 ns 7/8; **15.8 ns 5/8**, diagnostics 11/14.
Repeats are bit-identical, so the flow is deterministic.

**Primary comparison (best QoR, lower is better):**

| Method | Calls | Feasible | Fails | Best QoR |
|---|---|---|---|---|
| Random | 16 | 12 | 4 | 0.1695 |
| Optuna TPE | 16 | 13 | 3 | 0.1029 |
| Vanilla penalty BO | 16 | 16 | 0 | 0.1029 |
| FlowGuard-Raw | 16 | 11 | 5 | 0.1029 |
| FlowGuard-Calibrated | running | — | — | — |

The best configuration (`cand_014`: padding 0, GRT 0.20, AREA 0) was reached
independently by three methods. Its layout render and GDS are preserved under
`results/primary-optuna_tpe-v1/runs/trial_primary-optuna_tpe-cand_014/final/`.

## Repository layout

| Path | Contents |
|---|---|
| `src/runner.py` | deterministic single-trial LibreLane runner (Docker, pinned env, immutable trials) |
| `src/parser.py` | evidence parsing, worst-slack precedence, failure taxonomy, feasibility gate |
| `src/config_schema.py` | strict LibreLane 3.0.14 knob contract and canonical config hashing |
| `src/models.py` | feasibility Random Forest and feasible-only QoR Gaussian Process |
| `src/acquire.py` | risk-aware acquisition (EI x P(feasible)) |
| `src/primary_loop.py` | the five optimizer drivers + full AI provenance |
| `scripts/launch_*.sh` | campaign launchers (characterization hunts and primary comparison) |
| `designs/flowguard_fir/` | fixed CSD FIR, 428 cells, full timing/DRC/LVS pass |
| `designs/flowguard_stress/` | dense sensor MAC, 728 cells, the tuning target |
| `experiments/` | frozen manifests, pools, objective, analysis helper |
| `docs/OPERATOR_LOG.md` | append-only operator/experiment history |
| `docs/incidents/` | invalid-run incident records |

## Environment setup

The baseline pins LibreLane `3.0.14`, all Python dependency hashes, the
Linux/amd64 container digest, and the compatible Sky130 PDK revision. The
dependency lock targets Python 3.12. On Ubuntu with Docker available:

```bash
./scripts/openlane-setup.sh
./scripts/openlane-smoke.sh
./scripts/openlane-run.sh
./scripts/openlane-run.sh flowguard_fir
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
bash scripts/launch_clock_hunt.sh --namespace <namespace> \
  --hunt experiments/manifests/clock_hunt_15p8ns_v1.json --hours 5

# One primary optimizer method over the frozen pool
bash scripts/launch_primary_v1.sh --method flowguard_raw \
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
python3 -m unittest discover -s tests
```

The model/acquisition and primary-loop tests require numpy, scikit-learn,
scipy, and optuna (see `requirements.txt`).

## Related work

`chipignite/` is a data-only scaffold for screening external SKY130/Open-MPW
designs; the catalog tooling is offline and no external design has been
hardened by this project yet.

## Assumptions and limitations

- The 2x1 horizontal-abutment tile is an assumption, not a validated
  TinyTapeout/Oracle integration allocation.
- The stress design naturally produces a timing boundary; it does not generate
  routing/DRC failure diversity.
- Raw artifacts live on the experiment server; Git carries code, manifests,
  frozen contracts, and compact evidence only.

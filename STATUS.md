# FlowGuard Handoff Status

Last audited: 2026-09-11

## Current Branch

- Branch: `experiment/server-runs`
- Remote: `origin/experiment/server-runs`
- Current commit: `d6e43a6 Fix parser failure stage aggregation`
- Worktree: clean at the time of this update
- Recovery benchmark branch: `experiment/recovery-benchmark`
- Main foundation commit: `d44e3e2`
- FIR/data-pipeline feature commit: `4aa1bc7`

Do not rewrite or force-push this branch. Server result namespaces and failed
pilot records are immutable evidence.

## Verified Local Foundation

**[Done] Reproducible LibreLane/Sky130 environment**

- LibreLane `3.0.14`
- Digest-pinned Linux/amd64 container
- Sky130 revision `8afc8346a57fe1ab7934ba5a6056ea8b43078e71`
- Python 3.12 dependency lock
- Counter baseline completed all 80 flow stages with timing, DRC, and LVS pass

Primary files:

- `environment/openlane-baseline.env`
- `environment/librelane.lock`
- `scripts/openlane-setup.sh`
- `scripts/openlane-run.sh`
- `scripts/openlane-smoke.sh`
- `designs/flowguard_counter/`

## Hardware

### Primary CSD FIR

**[Done] `designs/flowguard_fir/`**

- Fixed signed coefficients: `[1, 2, 4, 8, 8, 4, 2, 1] / 32`
- Runtime coefficient storage and dynamic multiplier removed
- 428 synthesized cells
- 5,438.97 square micrometers synthesized area
- Full 80-stage LibreLane run passed timing, DRC, and LVS
- Fixed-tile utilization is below the 45% target
- Icarus simulation and Verilator lint pass

### Stress MAC

**[In Progress] `designs/flowguard_stress/`**

- Signed sensor MAC with input window, coefficient loading, folded arithmetic,
  and four-stage carry-lookahead pipeline
- Measured: 728 synthesized movable cells
- Fixed 1x1 effective utilization: 95.5%
- Global placement utilization: 109.884%
- Expected result: `GPL-0301` placement failure
- This is a stress/failure fixture, not currently a valid optimization benchmark

The repaired 2x1 candidate is:

- `designs/flowguard_stress/config.2x1.json`
- Assumption: two 160x100 micrometer tiles abut horizontally as a 320x100
  rectangle
- This geometry must be validated on the Oracle/TinyTapeout environment before
  claims are made.

## Python Data Pipeline

**[Done] Core single-trial stack**

- `src/runner.py`: isolated run directories, pinned interpreter selection,
  config hash, runtime provenance, stdout/stderr preservation, timeout/crash
  status, and LibreLane stage classification
- `src/parser.py`: metrics extraction, feasibility, immutable CSV/JSONL records
- `src/models.py`: RF feasibility model, feasible-only GP QoR model, small-data
  fallbacks
- `src/acquire.py`: EI multiplied by feasibility probability, risk threshold,
  frozen search definitions
- `src/config_schema.py`: strict allowlist, bounds, protected settings, legal
  `SYNTH_STRATEGY`, and rejection of legacy `CELL_PAD`

Tests currently pass: **17 unittest cases**.

Known local integration evidence:

- Four counter trials completed successfully.
- Parser extracted area, WNS/TNS, DRC, wirelength, and runtime.
- Model/acquisition fit completed on four records.

## Server Incident History

### `pilot_overfull_v0`

The first 24 stress trials are preserved as debug/pilot evidence only.

- Failure: `GPL-0301 Utilization 109.884% exceeds 100%`
- Failure stage: placement
- Valid for optimizer comparison: **no**
- Cause: the 1x1 fixed tile cannot contain the selected stress RTL
- Additional bugs found and fixed: invalid `CELL_PAD`, wrong launcher Python,
  generic `CRASH` classification, shared aggregate namespace

Incident files:

- `docs/incidents/overfull_pilot_v0.md`
- `experiments/incidents/pilot_overfull_v0.json`
- `results/server_experiment_manifest.csv`
- `results/server_experiment_v2_manifest.csv`

Raw LibreLane directories are intentionally not tracked in Git. They remain
server-local when available.

### Recovery pilot

Recovery tooling exists but the 2x1 geometry has not yet been accepted as a
validated TinyTapeout allocation.

- Manifest: `experiments/manifests/pilot_repaired_tile_v1.yaml`
- Launcher: `scripts/launch_oracle_campaign.sh`
- Namespace outputs: `results/<namespace>/`
- Stages: safe 3, middle 8, aggressive 16
- Clock: fixed at 20 ns
- Resume flag: `--resume`

The first v2 server attempt reached a real EDA `SUCCESS` for `safe-01` but hit
a parser CSV schema defect. That defect is fixed in `d6e43a6`. Treat the old v2
namespace as invalid parser evidence; use a new namespace such as
`pilot_repaired_tile_v3`.

## ChipIgnite Track

**[Scaffolded] `chipignite/`**

The data-only inventory and scoring tools cover the first three candidates:

1. `ee-uet/UETRV_ESoC_v2`
2. `binoy01/chipignite`
3. `dineshannayya/mbist_ctrl`

Implemented files:

- `chipignite/catalog_sources.yaml`
- `chipignite/catalog.py`
- `chipignite/inventory.py`
- `chipignite/scoring.py`
- `chipignite/report.py`
- `chipignite/__main__.py`
- `tests/test_chipignite.py`

The corpus has not yet been cloned, license-audited, migrated, or hardened.
Those are server/Internet-dependent follow-up tasks.

## Known Blockers

1. The stress 1x1 benchmark is structurally impossible and excluded from
   optimizer comparison.
2. The 2x1 horizontal-abutment assumption needs TinyTapeout/server validation.
3. The recovery launcher runs staged probes but does not yet implement the full
   online FlowGuard optimizer loop.
4. Hold timing, routing completion/overflow, signoff report links, and the
   canonical normalized objective are not complete in the parser.
5. Resume currently protects immutable artifacts but needs stronger repair of
   partially parsed trials.
6. Seeds are recorded by the launcher but are not yet propagated into all
   runner/model operations.
7. No external ChipIgnite modern baseline has been reproduced yet.
8. Dashboard and agentic DRC triage remain intentionally unstarted.

## Recovery Benchmark Update

The experimental branch adds the next correctness layer:

- `src/objective.py` computes normalized timing/wirelength/area objective
  components and rejects missing or zero denominators.
- `src/parser.py` preserves positive setup slack, parses hold/routing/DRC/LVS/
  signoff fields, captures `GPL_CELL_PADDING` and
  `PL_TARGET_DENSITY_PCT`, and rejects incomplete final evidence as feasible.
- `scripts/launch_oracle_campaign.sh` has preflight-only mode, safe-stage gate
  enforcement, immutable artifact manifests, and durable namespace status.
- `experiments/v3_analysis.py` provides offline range, repeatability, class
  balance, and feasible-only QoR sanity analysis.
- `experiments/manifests/v3_diagnostic_boundary.json` defines the next fixed-
  clock diagnostic boundary.

Corrected v3 evidence is now complete in the server-generated
`v3_corrected_aggregates_v7` output:

- 27/27 records have complete required evidence.
- 27/27 are feasible with DRC zero, LVS passed, and signoff passed.
- Setup worst slack is `3.863` to `4.915 ns`.
- Hold worst slack is `0.110` to `0.113 ns`.
- Area remains `15030.7` to `15318.4`; wirelength remains `27287` to `28897`.
- All 27 candidates are one feasibility class, so this is not yet a valid
  failure-aware optimization benchmark.

The corrected data proves the recovery instrument works. It also proves that
20 ns and the current 2x1 legal search region are too easy. Do not launch the
optimizer from this pilot.

## Next Agent Handoff

Work in this order:

1. Characterize fixed clocks at 17, 15, 13, and 11 ns with a safe config.
2. Choose one fixed clock with a feasible point and real failures.
3. Repeat three configurations at least three times to quantify noise.
4. Expand the diagnostic region until feasible and infeasible classes coexist.
5. Complete baseline/FlowGuard comparison only after a mixed region exists.
6. Mine and modernize the top three ChipIgnite candidates.

Server command:

```bash
git pull --ff-only origin experiment/recovery-benchmark
./scripts/openlane-setup.sh
bash scripts/launch_oracle_campaign.sh --preflight-only
```

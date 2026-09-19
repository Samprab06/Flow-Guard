# Clean physical validation of the completed crossbar v2 36-pool replay

Label: `CLEAN-PHYSICAL-VALIDATION-36POOL`. Live LibreLane reruns (2 trials),
no optimizer work, no commits.

## Frozen setup (pinned, unmodified)

* RTL: `designs/crossbar_datapath_v2/src/crossbar_datapath_v2.sv`
  (sha256 `e2848bb4…5407d37`).
* Clock 19.9 ns, footprint 320x200 (`DIE_AREA [0,0,320,200]`), `FP_CORE_UTIL 30`.
* Env: `environment/openlane-baseline.env` — LibreLane 3.0.14,
  `ghcr.io/librelane/librelane@sha256:f91b21d7…8280a30f`, PDK `sky130A`
  rev `8afc8346…78e71`, SCL `sky130_fd_sc_hd`, `PDK_ROOT /home/ubuntu/.ciel`.
* Oracle: `experiments/crossbar_v2/char36_results_ledger.json`;
  replay: `experiments/crossbar_v2/replay_36pool_offline/REPORT.md`
  (read-only; 9 traces, oracle-best QoR `-0.093068237` at knob-duplicate
  arms `cb36_002`/`cb36_006`/`cb36_010`).
* No edits to RTL, primary files (`src/*`), protocol, pool, or optimizer.
  Only new files: 2 clean configs + this validation dir. Nothing committed.

## Why these two trials

* `cb36_002` — overall best candidate; FlowGuard/EI-only headline winner
  (first-to-best on seeds 11/29/47). Knobs `AREA 0 / d35 / p2 / grt0.2`.
* `cb36_006` — materially different headline Vanilla winner (seed-11
  vanilla first-to-best at call 15). Knobs `AREA 0 / d45 / p2 / grt0.2`;
  differs from `cb36_002` by density (45 vs 35).
* No additional distinct winner needed: all 9 traces' best picks are
  `cb36_002` (8 traces) or `cb36_006` (seed-11 vanilla). `cb36_010`
  (d55, identical metrics) is never first-to-best in any trace.

## Exact commands (sequential, timeout 3600 s each, existing src.runner)

```
.venv/ml/bin/python -m src.runner --trial-id cb36_002_freshvalid01 \
  --config designs/crossbar_datapath_v2/characterization/config-freshvalid-cb36-002.json \
  --timeout 3600
.venv/ml/bin/python -m src.runner --trial-id cb36_006_freshvalid01 \
  --config designs/crossbar_datapath_v2/characterization/config-freshvalid-cb36-006.json \
  --timeout 3600
```

Clean configs are byte-identical in content to the banked effective configs:

| new trial | clean config | file sha256 | content hash | oracle match |
| --- | --- | --- | --- | --- |
| `cb36_002_freshvalid01` | `designs/crossbar_datapath_v2/characterization/config-freshvalid-cb36-002.json` | `34a9ef33…0c87eb6` | `dd00e1ff…6c5f188c` | exact |
| `cb36_006_freshvalid01` | `designs/crossbar_datapath_v2/characterization/config-freshvalid-cb36-006.json` | `451a5930…9cd6f17` | `33a62132…53a25f32e8` | exact |

Runner runs (git-ignored raw dirs preserved):

| new trial | raw run | started (UTC) | finished (UTC) | exit | runtime |
| --- | --- | --- | --- | --- | --- |
| `cb36_002_freshvalid01` | `designs/crossbar_datapath_v2/characterization/runs/trial_cb36_002_freshvalid01` | 2026-09-19T05:30:21Z | 2026-09-19T05:40:45Z | 0 / SUCCESS | 623.6 s (oracle 607.8 s) |
| `cb36_006_freshvalid01` | `designs/crossbar_datapath_v2/characterization/runs/trial_cb36_006_freshvalid01` | 2026-09-19T05:40:48Z | 2026-09-19T05:50:59Z | 0 / SUCCESS | 611.0 s (oracle 604.2 s) |

Runtime deltas (+15.8 s / +6.8 s) are wall-clock variance only.

## Metrics vs banked oracle (exact match on everything physical)

Oracle for both arms: setup_ws +0.19090329857261953, hold_ws +0.133669412655366,
wirelength 141422 um, area 37314.5 um2, crit 19.70909670142738 ns,
QoR -0.09306823743826212, DRC 0, routing 100, overflow null,
LVS pass, signoff pass, missing [].

| metric | cb36_002 fresh → oracle | cb36_006 fresh → oracle |
| --- | --- | --- |
| setup_ws | 0.19090329857261953 → MATCH | 0.19090329857261953 → MATCH |
| hold_ws | 0.133669412655366 → MATCH | 0.133669412655366 → MATCH |
| wirelength | 141422 → MATCH | 141422 → MATCH |
| area | 37314.5 → MATCH | 37314.5 → MATCH |
| critical delay | 19.70909670142738 → MATCH | 19.70909670142738 → MATCH |
| frozen QoR | -0.09306823743826212 → MATCH | -0.09306823743826212 → MATCH |
| DRC / routing / overflow | 0 / 100 / null → MATCH | 0 / 100 / null → MATCH |
| LVS / signoff / missing | pass / pass / [] → MATCH | pass / pass / [] → MATCH |
| feasible / status | true / SUCCESS → MATCH | true / SUCCESS → MATCH |

**Verdict: both trials MATCH the banked oracle on every physical/signoff metric.**

## Preserved artifacts (this dir)

* `cb36_002_freshvalid01.gds` (sha256 `10ca238e…3045806b`),
  `cb36_002_freshvalid01.png` (sha256 `35fbbd7e…a12dc5de`).
* `cb36_006_freshvalid01.gds` (sha256 `9d43b63d…00aefaa652`),
  `cb36_006_freshvalid01.png` (sha256 `35fbbd7e…a12dc5de`).
* Renders are byte-identical to both banked `artifacts_36pool/cb36_002.png`
  and `cb36_006.png` (`35fbbd7e…a12dc5de`). GDS byte hashes differ from the
  banked GDS (normal rerun stamping); all parsed physical metrics match exactly.
* Machine-readable: `validation_results.json` (this dir).

## Guardrails

No RTL, primary-file, protocol, pool, or optimizer modifications; no optimizer
launched (only `src.runner` + `src.parser`/`compute_qor` for scoring);
sequential execution; effective configs verified by sha256 + content hash;
nothing committed (`git status` shows only the 2 new clean configs + this dir
as untracked; raw runs are git-ignored).

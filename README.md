# FlowGuard

Failure-aware physical-design autotuning for LibreLane/OpenROAD and Sky130.

## Baseline

The baseline pins LibreLane `3.0.14`, all Python dependency hashes, the
Linux/amd64 container digest, and the compatible Sky130 PDK revision recorded
by that release. The dependency lock targets Python 3.12. On Ubuntu 24.04 with
Docker available to the current user:

```bash
./scripts/openlane-setup.sh
./scripts/openlane-smoke.sh
./scripts/openlane-run.sh
./scripts/openlane-run.sh flowguard_fir
```

`openlane-setup.sh` creates an ignored virtual environment, downloads the
pinned LibreLane container and PDK, and executes LibreLane's full smoke flow.
`openlane-run.sh` runs the repository's counter baseline and writes ignored
artifacts under `designs/flowguard_counter/runs/`.

## FIR Interface

`designs/flowguard_fir/` contains the fixed CSD signed 8-tap FIR. Its impulse
response is `[1,2,4,8,8,4,2,1]/32`; coefficients are not runtime programmable.
Each enabled sample produces a valid output one enabled clock later. `uio_in`
is reserved and `uio_oe` is fixed to the TinyTapeout input-only contract.

The CSD implementation measured 428 synthesized cells and passed the full
LibreLane timing/DRC/LVS flow. See `STATUS.md` for the prior folded and stress
design measurements.

See `TODO.md` for the complete implementation and experiment roadmap.

`designs/flowguard_stress/` is the companion dense sensor MAC target for
server-side tuning experiments. Its fixed-tile synthesis is intentionally
overfull and is used to retain failed placement/routing trials as evidence.

## Oracle Recovery Pilot

On a server with Docker, the pinned LibreLane environment, and this repository:

```bash
scripts/launch_oracle_campaign.sh \
  --namespace pilot_repaired_tile_v3 \
  --timeout 7200
```

This runs the staged 2x1 pilot: 3 safe, 8 middle, then 16 aggressive probes.
It keeps the clock fixed at 20 ns, preserves failed/timed-out trials, and
supports resume without overwriting completed records. For SSH execution from
a client:

```bash
ssh user@server 'cd /srv/flow-guard && bash scripts/launch_oracle_campaign.sh \
  --namespace pilot_repaired_tile_v3 --timeout 7200'
```

Pilot outputs are stored under `results/pilot_repaired_tile_v3/`. The 2x1
geometry is an explicit horizontal-abutment assumption and must be checked
against the server's TinyTapeout integration environment before treating the
pilot as a final benchmark.

The current recovery branch tip is `d6e43a6` or newer. Use a new namespace for
every changed manifest/config/flow version; never overwrite earlier pilot data.

The stricter metric/objective and diagnostic-boundary work lives on the
experimental branch `experiment/recovery-benchmark` until the next pilot is
validated. It intentionally does not change `main`.

## ChipIgnite Inventory

The external-corpus tooling is data-only:

```bash
python3 -m chipignite catalog --output chipignite/catalog.json
python3 -m chipignite report chipignite/catalog.json --output chipignite/ranking.json
```

## Branches

- `feature/openlane-baseline`: environment and baseline flow
- `feature/runner-parser`: isolated trials and evidence parsing
- `feature/models-acquisition`: feasibility/QoR models and candidate selection
- `feature/dashboard`: cached experiment dashboard
- `chore/project-foundation`: repository planning and maintenance

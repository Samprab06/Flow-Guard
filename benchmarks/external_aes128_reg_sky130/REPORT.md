# External AES-128 SKY130 wrapper variant — status report

Namespace: `external_aes128_reg_sky130`. Isolated wrapper variant of the
`external_aes128_sky130` benchmark: new paths only, no primary FlowGuard
file modified, no `designs/openroad_aes128_sky130/` file modified, no
FlowGuard algorithm change, no new dependencies. Upstream RTL copies are
bit-identical (sha256) to the unwrapped design.

- Benchmark manifest: `benchmarks/external_aes128_reg_sky130/manifest.json`
- Wrapper design: `designs/openroad_aes128_reg_sky130/` (+ `ATTRIBUTION.md`)
- Upstream: https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts
  (same pinned revision `95ebc50a258390f4c7896e5f04db743f62279c2d`)
- New logic (only addition): `src/aes_cipher_top_reg.v` — registers
  `ld`/`key`/`text_in` at the boundary, instantiates upstream
  `aes_cipher_top` verbatim, passes `done`/`text_out` through. Same port
  list as the core; one extra cycle of latency (done ~13 cycles after the
  wrapper `ld` pulse vs ~12).
- Baseline clock: 20.0 ns (same conservative gate as unwrapped baseline, so
  the trial isolates exactly one variable: input registering).
- Tool pins reused unchanged: LibreLane 3.0.14, same container digest,
  sky130A PDK rev `8afc8346a57fe1ab7934ba5a6056ea8b43078e71`.

## Gate 1a — functional verification: PASS

Command: `./benchmarks/external_aes128_reg_sky130/run_verify.sh`
(log: `benchmarks/external_aes128_reg_sky130/verify_work/verify.log`)

- Oracle reused verbatim: `../external_aes128_sky130/gen_vectors.py`
  (`cryptography` 42.0.0 AES-ECB, seed `0xA35`; vectors copied locally).
- 38/38 vectors correct: 3 FIPS-197 KAT
  (`69c4e0d86a7b0430d8cdb78070b4c55a`, all-zero
  `66e94bd4ef8a2c3b884cfa59ca342b2e`, all-ones `bcbf217cb280cf30b2517052193ab979`)
  + 32 seeded-random + 3 structured edge cases.
- Protocol: `rst` active-low; `done` low after reset release with no `ld`;
  `done` low during compute; single-cycle `done` pulse (13 cycles after
  wrapper `ld`, i.e. one extra cycle vs the core); mid-operation reset
  aborts (no `done` within 25 cycles); post-reset recovery op passes.
- Tools: Icarus Verilog 12.0, Python 3.12.3.

## Gate 1b — synthesis sanity: PASS

- `verilator --lint-only --no-timing --top-module aes_cipher_top_reg`
  (with `+incdir+src` for `timescale.v`): clean, exit 0, no warnings
  (Verilator 5.020).
- Yosys generic synth in the pinned LibreLane container: 10,705 cells
  (+257 vs the unwrapped 10,448 — exactly the 1 + 128 + 128 wrapper
  registers), hierarchy clean (1× `aes_cipher_top` submodule, no
  blackboxes). Yosys 0.62.

## Gate 1c — conservative LibreLane baseline: COMPLETE, INFEASIBLE (stop)

- Trial: `aes128-reg-conservative-baseline-v1`, config
  `designs/openroad_aes128_reg_sky130/config.json`
  (`FP_CORE_UTIL 35`, `PL_TARGET_DENSITY_PCT 45`, 20 ns).
- Runner: `SUCCESS`, exit 0, runtime 2633 s (~44 min), all 76 stages +
  `final/` (DEF/GDS/LEF/LIB/SDC/SDF/SPEF/SPICE + `metrics.json`) present.
  Runner log: `benchmarks/external_aes128_reg_sky130/baseline_runner.log`.
  Ledger: `benchmarks/external_aes128_reg_sky130/baseline_v1/aggregated.{csv,jsonl}`.
- Parser verdict: **TIMING_FAIL / feasible=false**.
  Area 132448 (+12% vs unwrapped 118222 — the 257 wrapper flops), routed
  wirelength 639354, routing completion 100, routing DRC violations 0,
  Magic DRC 0, LVS true, signoff true, hold_ws +0.099 (passes all hold
  corners), missing metrics [].
- Setup by corner (post-PnR STA): max_ss_100C_1v60 **-1.076** (12 violated
  paths), nom_ss_100C_1v60 -0.529 (5 paths); all other corners pass with
  margin (e.g. max_tt +8.77, nom_tt +9.07, max_ff +12.64).
- The `ld`-input artifact is **eliminated**: zero input-port violations
  (unwrapped baseline had all 32 violations starting at `ld`). All 17
  remaining violations are **reg-to-reg** (flop-to-flop round-datapath
  paths, e.g. `_17454_` → `_17560_` at -1.076) — the combinational round
  logic (S-box/MixColumn/key-expand depth) does not close 20 ns at the SS
  corner. This is now **architecturally timing-limited**, not closable by
  FlowGuard placement/density knobs.
- Decision per task policy (architecturally timing-limited → stop,
  document): no characterization batch; no optimizer comparison; no
  further EDA spend. (Max-slew warning counts are comparable to the
  unwrapped baseline — 7376 vs 7086 at max_ss — and are not part of the
  parser feasibility gate.)

## Provenance / integrity notes

- `src/runner.py`, `src/parser.py`, `src/config_schema.py`,
  `environment/openlane-baseline.env`, all primary manifests/pools,
  `pitch/`, `designs/openroad_aes128_sky130/`, and
  `benchmarks/external_aes128_sky130/` were read but not modified.
- New paths: `designs/openroad_aes128_reg_sky130/`,
  `benchmarks/external_aes128_reg_sky130/`.
- Untracked runtime paths: `designs/openroad_aes128_reg_sky130/runs/`
  (gitignored by existing rule),
  `benchmarks/external_aes128_reg_sky130/verify_work/`,
  `benchmarks/external_aes128_reg_sky130/vectors.hex` (copy of oracle output).

# External AES-128 SKY130 benchmark — status report

Namespace: `external_aes128_sky130`. Isolated from the primary FlowGuard
experiment: new paths only, no primary file modified, no FlowGuard
algorithm change, no new dependencies.

- Benchmark manifest: `benchmarks/external_aes128_sky130/manifest.json`
- Vendored design: `designs/openroad_aes128_sky130/` (+ `ATTRIBUTION.md`)
- Upstream: https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts
- Pinned revision: `95ebc50a258390f4c7896e5f04db743f62279c2d`
  (upstream `master` HEAD as resolved by `git ls-remote` on 2026-09-18)
- RTL: `flow/designs/src/aes/` (`aes_cipher_top` + key-expand/rcon/sbox;
  inverse-cipher files vendored but excluded from build)
- Reference flow: `flow/designs/sky130hd/aes/config.mk`
  (`CORE_UTILIZATION = 35`, SDC 3.6 ns — NOT reused as baseline clock)
- Baseline clock: 20.0 ns (conservative first gate; top-level + nested SCL)
- Tool pins reused unchanged: LibreLane 3.0.14,
  container `ghcr.io/librelane/librelane@sha256:f91b21d75f79871f9ccf37451020b5d2f7b3236881a997ff709c561e8280a30f`,
  sky130A PDK rev `8afc8346a57fe1ab7934ba5a6056ea8b43078e71`
  (from `environment/openlane-baseline.env`; file itself untouched)

## Gate 1a — functional verification: PASS

Command: `./benchmarks/external_aes128_sky130/run_verify.sh`
(log: `benchmarks/external_aes128_sky130/verify_work/verify.log`)

- Oracle: `cryptography` 42.0.0 AES-ECB (OpenSSL-backed; shares no code
  with the OpenCores/ORFS RTL). Generator:
  `benchmarks/external_aes128_sky130/gen_vectors.py` (seed `0xA35`).
- 38/38 vectors correct: 3 FIPS-197 KAT (Appendix B
  `69c4e0d86a7b0430d8cdb78070b4c55a`, Appendix A all-zero
  `66e94bd4ef8a2c3b884cfa59ca342b2e`, all-ones oracle-computed) +
  32 seeded-random + 3 structured edge cases.
- Protocol: `rst` active-low; `done` low after reset release with no `ld`;
  `done` low during compute; single-cycle `done` pulse (~12 cycles after
  `ld`); mid-operation reset aborts (no `done` within 25 cycles);
  post-reset recovery op passes.
- TB note (fixed during bring-up, RTL untouched): `text_out` is
  re-registered every cycle and valid ONLY on the `done` cycle; the TB
  captures it on `done` before checking pulse width. `timescale.v`
  resolved via `-I src`.
- Tools: Icarus Verilog 12.0, Python 3.12.3.

## Gate 1b — synthesis sanity: PASS

- `verilator --lint-only --no-timing --top-module aes_cipher_top`: clean,
  exit 0, no warnings (Verilator 5.020; `--no-timing` covers the RTL's
  simulation-only `#1` intra-assignment delays).
- Yosys generic synth in the pinned LibreLane container: 10,448 cells,
  514 flops, hierarchy clean (16× `aes_sbox` + `aes_key_expand_128`,
  no blackboxes). Yosys 0.62 (git `7326bb7d6641500ecb285c291a54a662cb1e76cf`).
- In-flow sky130 mapping (`06-yosys-synthesis/reports/post_dff.json`):
  10,445 mapped cells incl. 562 `sky130_fd_sc_hd__dfxtp_2` flops.

## Gate 1c — conservative LibreLane baseline: COMPLETE, INFEASIBLE (stop)

- Trial: `aes128-conservative-baseline-v1`, config
  `designs/openroad_aes128_sky130/config.json`
  (`FP_CORE_UTIL 35`, `PL_TARGET_DENSITY_PCT 45`, 20 ns).
- Runner: `SUCCESS`, exit 0, runtime 2018 s (~34 min), all 80 stages,
  `status.json` + `final/` (GDS 24 MB, MAG, LEF, LIB, SDC, SPEF, SDF,
  SPICE) present. Ledger:
  `benchmarks/external_aes128_sky130/baseline_v1/aggregated.{csv,jsonl}`.
- Parser verdict: **TIMING_FAIL / feasible=false**.
  Area 118222, routed wirelength 595677, routing completion 100,
  routing DRC violations 0, Magic DRC 0, LVS true, signoff true,
  hold_ws +0.108 (passes all hold corners), missing metrics [].
- Setup by corner (post-PnR STA): max_ss_100C_1v60 **-3.885** (32
  violated paths), nom_ss_100C_1v60 -3.250; max_ff +9.138, max_tt
  +5.504, nom_ff +9.362, nom_tt +5.844 (pass with margin).
- Exact blocker: **all 32 violating paths start at the unregistered `ld`
  input port** (4 ns input external delay per the standard 20%-of-period
  fallback SDC, then ~21 ns of buffer/comb depth:
  buf → inv → clkbuf/clkdlybuf fanout tree → nor2/or3b/a31o/o221a to
  562+ flop D pins; data arrival 25.3 ns vs 21.4 ns required).
  Zero flop→flop violations — the round datapath closes 20 ns; `key` /
  `text_in` input paths also pass. This is an integration-boundary
  artifact (in-system `ld` would be register-driven), not closable by
  FlowGuard placement/density knobs (logic depth + fanout, not
  congestion: routing completed with 0 violations).
- Decision per gate policy (no valid baseline → stop, document):
  characterization batch `aes128-char-v1` is NOT run; no optimizer
  comparison; no further EDA spend. Candidate next steps for lead
  approval only: (a) thin input-registering wrapper as a new design
  variant (upstream RTL pristine; wrapper needs re-verification via
  `run_verify.sh` against the same oracle); (b) slower-clock probe to
  find the feasible boundary; (c) ORFS-style SDC/knob treatment
  comparison. Representative evidence retained: `final/` reports+GDS
  (run dir gitignored), `baseline_v1/` ledger (tracked-candidate).

## Provenance / integrity notes

- `src/runner.py`, `src/parser.py`, `src/config_schema.py`,
  `environment/openlane-baseline.env`, all primary manifests/pools, and
  `pitch/` were read but not modified.
- New tracked paths: `designs/openroad_aes128_sky130/`,
  `benchmarks/external_aes128_sky130/` (code + manifest + this report).
- Untracked runtime paths (lead decides on commit):
  `designs/openroad_aes128_sky130/runs/` (gitignored by existing rule),
  `benchmarks/external_aes128_sky130/verify_work/` (TB binary + log),
  `benchmarks/external_aes128_sky130/vectors.hex|json` (regenerable at any
  time via `gen_vectors.py`; kept on disk for rerun provenance).

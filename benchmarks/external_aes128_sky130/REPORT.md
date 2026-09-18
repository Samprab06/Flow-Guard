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

## Gate 1c — conservative LibreLane baseline: RUNNING (interim)

- Trial: `aes128-conservative-baseline-v1`, config
  `designs/openroad_aes128_sky130/config.json`
  (`FP_CORE_UTIL 35`, `PL_TARGET_DENSITY_PCT 45`, 20 ns).
- Config preflight (`src.config_schema.validate_config`): OK.
- Launch (detached, per operator rule — one `setsid nohup` per call):
  `setsid nohup python3 -m src.runner --trial-id
  aes128-conservative-baseline-v1 --config
  designs/openroad_aes128_sky130/config.json --timeout 7200`
  (log: `benchmarks/external_aes128_sky130/baseline_runner.log`).
- Raw run (gitignored by design):
  `designs/openroad_aes128_sky130/runs/trial_aes128-conservative-baseline-v1/`.
- Six-hour-style cap: runner tool timeout 7200 s; campaign budget cap
  21600 s per `manifest.json`. If the flow has no valid baseline by cap,
  stop and record the exact stage/error here.
- On success: parse with `src.parser` (reuse, unmodified), require
  FEASIBLE (`setup_ws >= 0`, `hold_ws >= 0`, routing 100, DRC 0,
  LVS + signoff true, no missing metrics), then run ONLY the 4-trial
  prespecified `aes128-char-v1` batch from `manifest.json`
  (2 determinism repeats + density-60 + synth-AREA1 probes at frozen
  20 ns). No broad optimizer comparison before status is reported.

## Blockers

None yet. Baseline flow was progressing normally at report time
(through `06-yosys-synthesis`, at `10-openroad-checksdcfiles`).

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

# Attribution: AES-128 input-registering wrapper (`aes_cipher_top_reg`)

Isolated wrapper-variant benchmark `benchmarks/external_aes128_reg_sky130/`
+ `designs/openroad_aes128_reg_sky130/`. New paths only; no primary
FlowGuard file, no `designs/openroad_aes128_sky130/` file, and no upstream
RTL content was modified.

## Upstream (same as `designs/openroad_aes128_sky130/ATTRIBUTION.md`)

- Repository: https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts
- Pinned revision: `95ebc50a258390f4c7896e5f04db743f62279c2d`
- Original core: Rudolf Usselmann (`rudi@asics.ws`), via OpenCores
  `aes_core`; per-file copyright headers retained verbatim.
- License text copied as `src/LICENSE.upstream` (from
  http://asics.ws/v6/free-ip-cores, via ORFS `flow/designs/src/aes/LICENSE`).
  Derivative work keeps the original copyright notice per that license.

## Files

- Pristine upstream copies in `src/` (sha256 identical to
  `designs/openroad_aes128_sky130/src/`):
  - `aes_cipher_top.v`
    `ab39a4a094dc8cfde90fcaa4c1aaf7dc9bf75b57ed762e11a985b88f6b23996c`
  - `aes_key_expand_128.v`
    `bf06921c6fe80a69674f8b38160e8d677e1c4cc1a96befee2ac136bed3fe48c6`
  - `aes_rcon.v`
    `1e8a0d1f8c3da8d382adb94e98bacfab455683ca3bca282b982179c0f7607e8e`
  - `aes_sbox.v`
    `7f4fe4173d58017eb2520fb130b3b779d63a373463cb0198bd66c4371184d7fb`
  - `timescale.v`
    `0833b736793bc11f640ed66357614c0f5cf30a548a7e515333b1e46438b2cb6b`
  - `LICENSE.upstream`
    `628b5468499d9dbe5bfbc6271b854a1112461ca308acae42db173d3b10c09331`
- New file (only functional addition in this namespace):
  - `src/aes_cipher_top_reg.v` — thin wrapper: registers `ld`/`key`/
    `text_in` on `clk` (active-low `rst` clears to 0), instantiates
    upstream `aes_cipher_top` verbatim, passes `done`/`text_out` through.
    Same port list as the core; one extra cycle of latency.

## Local benchmark choices

- Build top is `aes_cipher_top_reg` (`config.json`); inverse-cipher files
  are not vendored into this variant at all.
- Conservative clock 20.0 ns, `FP_CORE_UTIL 35`,
  `PL_TARGET_DENSITY_PCT 45` — identical to the unwrapped baseline, so the
  single wrapper trial isolates exactly one variable (input registering).
- Oracle/testbench reuse: `benchmarks/external_aes128_reg_sky130/`
  reuses `benchmarks/external_aes128_sky130/gen_vectors.py` verbatim
  (same seed `0xA35`, same 38 vectors); the wrapper testbench
  `tb_aes_reg_verify.v` is the same protocol with the DUT swapped to
  `aes_cipher_top_reg`.

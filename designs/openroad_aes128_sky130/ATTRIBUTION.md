# Attribution: OpenROAD AES-128 (`aes_cipher_top`)

Vendored RTL for the isolated external FlowGuard benchmark
`benchmarks/external_aes128_sky130/`. This directory adds new files only;
no primary FlowGuard design, manifest, pool, objective, or source file was
modified.

## Upstream

- Repository: https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts
- Pinned revision: `95ebc50a258390f4c7896e5f04db743f62279c2d`
  (upstream `master` HEAD as resolved on 2026-09-18; `git ls-remote`).
- RTL path: `flow/designs/src/aes/`
- Flow reference: `flow/designs/sky130hd/aes/config.mk`
  (`DESIGN_NAME = aes_cipher_top`, `PLATFORM = sky130hd`,
  `CORE_UTILIZATION = 35`, SDC clock period 3.6 ns in
  `flow/designs/sky130hd/aes/constraint.sdc`).
- Upstream provenance note (`flow/designs/src/aes/README.md`): "Simple AES
  (Rijndael) IP Core", downloaded from
  https://opencores.org/projects/aes_core on 8/8/2019; SDC constraints
  added and Verilog updated to standard attributes by ORFS.

## Original author / license

- Original core: Rudolf Usselmann (`rudi@asics.ws`), via OpenCores
  `aes_core`; per-file copyright headers retained verbatim.
- License text vendored as `src/LICENSE.upstream` (from
  http://asics.ws/v6/free-ip-cores, via ORFS `flow/designs/src/aes/LICENSE`).
  Derivative work keeps the original copyright notice per that license.

## Files vendored (unmodified, sha256)

- `src/aes_cipher_top.v` `ab39a4a094dc8cfde90fcaa4c1aaf7dc9bf75b57ed762e11a985b88f6b23996c`
- `src/aes_key_expand_128.v` `bf06921c6fe80a69674f8b38160e8d677e1c4cc1a96befee2ac136bed3fe48c6`
- `src/aes_rcon.v` `1e8a0d1f8c3da8d382adb94e98bacfab455683ca3bca282b982179c0f7607e8e`
- `src/aes_sbox.v` `7f4fe4173d58017eb2520fb130b3b779d63a373463cb0198bd66c4371184d7fb`
- `src/timescale.v` `0833b736793bc11f640ed66357614c0f5cf30a548a7e515333b1e46438b2cb6b`
- `src/aes_inv_cipher_top.v` `2f629dab66518aac9e76cb7dbbcf9365785e02531aadcca0cff8f4eb62c963a6` (vendored for completeness; NOT in build)
- `src/aes_inv_sbox.v` `ce684a8941f3bd0a1b1345bcb4eb1cff01399a28935f89ce5b8e0be31652bbb2` (vendored for completeness; NOT in build)
- `src/LICENSE.upstream` `628b5468499d9dbe5bfbc6271b854a1112461ca308acae42db173d3b10c09331`

## Local benchmark choices (deliberate deviations from upstream)

- Build list (`config.json`) contains only the encryption datapath
  (`aes_cipher_top`, `aes_key_expand_128`, `aes_rcon`, `aes_sbox`); the
  inverse-cipher files are excluded from synthesis.
- Conservative benchmark clock is 20.0 ns (top-level and nested SKY130 SCL
  override), NOT the upstream 3.6 ns SDC, which is an aggressive
  signoff target unsuitable for a first baseline gate.
- Die sizing is utilization-based (`FP_CORE_UTIL 35`,
  `PL_TARGET_DENSITY_PCT 45`), mirroring the FlowGuard counter baseline.
- `timescale.v` is pulled in via the RTL `` `include `` directive; it is not
  listed in `VERILOG_FILES`.

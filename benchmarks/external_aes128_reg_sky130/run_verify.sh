#!/usr/bin/env bash
# Gate 1a (wrapper variant): functional verification of aes_cipher_top_reg.
# Reuses the existing independent oracle generator verbatim
# (benchmarks/external_aes128_sky130/gen_vectors.py, cryptography/OpenSSL,
# seed 0xA35); compiles the wrapper + pristine upstream RTL copies in
# designs/openroad_aes128_reg_sky130/src and runs the wrapper testbench
# (same 38 vectors + reset/done protocol checks).
set -euo pipefail
here="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
base="$here/../external_aes128_sky130"
design="$here/../../designs/openroad_aes128_reg_sky130/src"
work="$here/verify_work"
mkdir -p "$work"
python3 "$base/gen_vectors.py"
cp "$base/vectors.hex" "$here/vectors.hex"
cp "$here/vectors.hex" "$work/vectors.hex"
iverilog -Wall -I "$design" -o "$work/tb.vvp" \
  -y "$design" \
  "$here/tb_aes_reg_verify.v" "$design/aes_cipher_top_reg.v" \
  "$design/aes_cipher_top.v" \
  "$design/aes_key_expand_128.v" "$design/aes_rcon.v" "$design/aes_sbox.v" \
  "$design/timescale.v"
(cd "$work" && vvp tb.vvp | tee verify.log)
grep -q "VERIFY-PASS" "$work/verify.log"

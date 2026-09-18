#!/usr/bin/env bash
# Gate 1a: functional verification of vendored aes_cipher_top.
# Generates oracle vectors (cryptography/OpenSSL, independent of RTL),
# compiles with Icarus Verilog, runs the self-checking testbench.
set -euo pipefail
here="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
design="$here/../../designs/openroad_aes128_sky130/src"
work="$here/verify_work"
mkdir -p "$work"
python3 "$here/gen_vectors.py"
cp "$here/vectors.hex" "$work/vectors.hex"
iverilog -Wall -I "$design" -o "$work/tb.vvp" \
  -y "$design" \
  "$here/tb_aes_verify.v" "$design/aes_cipher_top.v" \
  "$design/aes_key_expand_128.v" "$design/aes_rcon.v" "$design/aes_sbox.v" \
  "$design/timescale.v"
(cd "$work" && vvp tb.vvp | tee verify.log)
grep -q "VERIFY-PASS" "$work/verify.log"

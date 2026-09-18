"""Generate AES-128 verification vectors from an independent implementation.

Independent oracle: the `cryptography` package (OpenSSL-backed AES-ECB),
which shares no code with the vendored OpenCores/ORFS RTL.
Includes FIPS-197 Appendix A/B known-answer vectors plus seeded randomized
vectors. Output: vectors.hex (one 384-bit row per vector: key_pt_ct).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

HERE = Path(__file__).resolve().parent
N_RANDOM = 32
RANDOM_SEED = 0xA35


def aes128_ecb_encrypt(key: bytes, plaintext: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(plaintext) + encryptor.finalize()


def main() -> None:
    # FIPS-197 known answers (fixed; also cross-checked against oracle below).
    kats = [
        # Appendix B
        ("000102030405060708090a0b0c0d0e0f",
         "00112233445566778899aabbccddeeff",
         "69c4e0d86a7b0430d8cdb78070b4c55a"),
        # Appendix A (all-zero key/plaintext)
        ("00000000000000000000000000000000",
         "00000000000000000000000000000000",
         "66e94bd4ef8a2c3b884cfa59ca342b2e"),
        # All-ones
        ("ffffffffffffffffffffffffffffffff",
         "ffffffffffffffffffffffffffffffff",
         None),
    ]
    rows: list[tuple[str, str, str]] = []
    for key_h, pt_h, ct_h in kats:
        ct = ct_h or aes128_ecb_encrypt(bytes.fromhex(key_h), bytes.fromhex(pt_h)).hex()
        if ct_h is not None:
            assert aes128_ecb_encrypt(bytes.fromhex(key_h), bytes.fromhex(pt_h)).hex() == ct_h, \
                f"oracle disagrees with FIPS-197 KAT {key_h}"
        rows.append((key_h, pt_h, ct))

    rng = random.Random(RANDOM_SEED)
    for _ in range(N_RANDOM):
        key = bytes(rng.randrange(256) for _ in range(16))
        pt = bytes(rng.randrange(256) for _ in range(16))
        # Mix structured edge cases into the random stream deterministically.
        rows.append((key.hex(), pt.hex(), aes128_ecb_encrypt(key, pt).hex()))
    # Deterministic edge cases (oracle-computed).
    edge = [
        ("000102030405060708090a0b0c0d0e0f", "00000000000000000000000000000000"),
        ("00000000000000000000000000000000", "00112233445566778899aabbccddeeff"),
        ("2b7e151628aed2a6abf7158809cf4f3c", "3243f6a8885a308d313198a2e0370734"),
    ]
    for key_h, pt_h in edge:
        rows.append((key_h, pt_h,
                     aes128_ecb_encrypt(bytes.fromhex(key_h), bytes.fromhex(pt_h)).hex()))

    with (HERE / "vectors.hex").open("w", encoding="utf-8") as fh:
        for key_h, pt_h, ct_h in rows:
            fh.write(f"{key_h}{pt_h}{ct_h}\n")
    with (HERE / "vectors.json").open("w", encoding="utf-8") as fh:
        json.dump(
            {"oracle": "cryptography(AES-ECB)/OpenSSL", "seed": RANDOM_SEED,
             "count": len(rows),
             "vectors": [{"key": k, "pt": p, "ct": c} for k, p, c in rows]},
            fh, indent=2)
        fh.write("\n")
    print(f"wrote {len(rows)} vectors ({len(kats)} KAT + {N_RANDOM} random + {len(edge)} edge)")


if __name__ == "__main__":
    main()

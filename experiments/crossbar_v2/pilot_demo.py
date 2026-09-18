#!/usr/bin/env python3
"""Replayable six-call crossbar v2 pilot demo (characterization cache only).

Runs the EXISTING six-call pilot (2 shared init + 4 adaptive, seeds
1337/1339/1340 over the frozen 6-candidate pool) and writes a
timestamped, clearly labeled PILOT result snapshot.

Guarantees:
  * No RTL edits, no primary-file edits.
  * No optimizer runs and no EDA/LibreLane launches. Each policy only
    reads deterministic characterization-cache outcomes through
    ``compare_replay.candidate_rows`` / ``compare_replay.replay``
    (``src/parser.build_record`` + frozen ``src/primary_loop`` drivers).
  * Does NOT rewrite ``frozen_manifest.json``, ``comparison_results.json``,
    ``REPORT.md``, or the new 24-call protocol manifest
    ``eval_protocol_v2_frozen.json``. The 24-call comparison stays pending.

Usage:
  python3 experiments/crossbar_v2/pilot_demo.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "crossbar_v2"))

from compare_replay import candidate_rows, replay  # noqa: E402  (cache replay only; no runner/EDA import)

OUT_DIR = ROOT / "experiments" / "crossbar_v2" / "pilot_demo_results"

PILOT_METHODS = [
    ("default", 1337),
    ("vanilla_bo", 1339),
    ("flowguard_raw", 1340),
]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pool = candidate_rows()
    results = [replay(method, pool, seed) for method, seed in PILOT_METHODS]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot = {
        "label": "PILOT-DEMO-SIX-CALL",
        "note": "Replayable pilot snapshot over the existing frozen 6-candidate pool (2 shared + 4 adaptive). NOT the frozen 24-call protocol comparison (8 shared + 16 adaptive, seeds 11/29/47), which remains pending.",
        "created_utc": stamp,
        "budget_per_method": 6,
        "shared_init_ids": ["cand_001", "cand_002"],
        "methods": [method for method, _ in PILOT_METHODS],
        "seeds": [seed for _, seed in PILOT_METHODS],
        "data_source": "characterization_cache",
        "physical_runs_launched": 0,
        "protocol_manifest": "experiments/crossbar_v2/eval_protocol_v2_frozen.json",
        "source_pool_manifest": "experiments/crossbar_v2/frozen_manifest.json",
        "results": results,
    }
    path = OUT_DIR / f"pilot_demo_sixcall_{stamp}.json"
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    print(f"PILOT demo snapshot: {path}")
    print(f"label={snapshot['label']} budget=6 methods={snapshot['methods']} seeds={snapshot['seeds']}")
    print("physical_runs_launched=0 (characterization-cache replay only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

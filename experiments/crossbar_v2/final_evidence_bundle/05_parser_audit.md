# Parser audit evidence

- Audit doc: `experiments/PARSER_AUDIT.md` (commits `76d0bf0`, `68ab3f3`).
- Corrected setup_ws precedence: `src/parser.py:164-166` — `WNS = setup_ws` if present else `setup_wns`; `*_wns` are violation-only (0 when clean), so worst slack is canonical. Launcher fallback `src/parser.py:89-90` (`setup_ws` else `setup_wns`) for critical delay.
- Test: `tests/test_parser.py:62-67` verifies positive worst slack (3.9) takes precedence over zero violation-only WNS.
- Ledger `experiments/crossbar_v2/char36_results_ledger.json` stores nested `parser_record.{WNS, setup_wns, setup_ws}` per candidate; `experiments/crossbar_v2/replay_36pool_offline.py` + ext10 read only that ledger and never recompute/clamp timing.

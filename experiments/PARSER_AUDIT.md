# Timing Evidence Audit

Audit date: 2026-09-19. Scope: reported primary `tt_um_flowguard_stress`
results and the crossbar v2 measured-oracle/replay results. No primary or
crossbar result was changed by this audit.

## Corrected parser

- `src/parser.py:145-168` extracts `timing__setup__ws` and uses setup worst
  slack as canonical `WNS`; violation-only `setup_wns` is retained separately.
- `src/parser.py:187-207` applies the corrected feasibility rule, including
  setup/hold, hold violations, routing completion/overflow, DRC, LVS, signoff,
  and missing metrics.
- `tests/test_parser.py:62-67` explicitly verifies that positive worst slack
  takes precedence over a zero violation-only WNS.

## Primary results

- The frozen primary benchmark manifest is `experiments/manifests/primary_benchmark_v1.json`.
- The project dossier records the prior parser correction at
  `docs/PROJECT_DOSSIER.md:294-296`, before the frozen primary comparison
  summary at `docs/PROJECT_DOSSIER.md:261-275`.
- Primary optimizer ledgers are local-only, but the reported primary sequence
  is the corrected post-fix sequence; no stale/clamped timing sequence was
  found requiring rebuild.

## Crossbar results

- `experiments/crossbar_v2/char36_results_ledger.json` was produced through
  `src.parser.build_record` and stores parser records, corrected setup slack,
  feasibility checks, runtimes, and physical artifacts for all 36 points.
- `experiments/crossbar_v2/replay_36pool_offline.py` and the 13-seed extension
  read only that measured ledger. They do not recompute or clamp timing values.
- The 36-point oracle contains 6 feasible and 30 infeasible candidates. The
  feasible QoR range is `-0.093068237` to `0.311299618`.
- Replay provenance, selected IDs, and cumulative empirical EDA time are
  recorded in the committed replay result files; no stale crossbar replay was
  found requiring rebuild.

## Conclusion

All reported primary and crossbar results audited here use corrected worst
slack evidence. The crossbar extension is an offline measured-oracle replay,
not a claim of additional physical optimizer runs.

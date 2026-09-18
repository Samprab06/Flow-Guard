# Submission Audit

Audit scope: FlowGuard-recovery and the external TinyTapeout artifact tree, excluding the isolated AES workstream and the frozen primary experiment.

## Verdict

Not ready for an unqualified generalization claim. The committed pitch is restricted to the frozen primary evidence and explicitly separates local-only raw EDA artifacts from Git-tracked manifests and renders.

## Passing checks

- Frozen benchmark manifest, objective, candidate pool, and characterization manifests are present.
- The candidate pool contains 72 unique IDs.
- Fresh validation has three default and three `cand_014` runs; all are feasible and signoff-clean.
- 722 available GDS files were rendered with zero failures using the existing LibreLane/KLayout settings. See `pitch/renders/MANIFEST.md`.

## Warnings and blockers

- Primary raw ledgers are local-only and are not committed.
- Fresh comparison provenance records a dirty source tree and a pool hash differing from the frozen primary manifest.
- The exhaustive sweep contains 485 rows but 484 unique trial IDs; the duplicate cannot be resolved without the absent source ledger.
- The calibrated method is queued/incomplete; the comparison is not a complete five-way result.
- Cross-design and classifier artifacts are not used for headline claims.

## Claim policy

- Use `experiments/objective_qor_v1.json`, not the legacy `src/objective.py`, for production QoR.
- Report FlowGuard-Raw as reaching the best QoR at adaptive call 11 with 11/16 feasible adaptive trials.
- Do not claim fewer failures, a general speedup, or generalization from a valid GDS alone.
- Treat the committed PNGs as verified layout renders; raw GDS and ledgers remain server-local.

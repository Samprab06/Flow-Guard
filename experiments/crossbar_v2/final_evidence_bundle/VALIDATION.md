# Validation checks (all must pass)

- final bundle commit `f0fa483`; final worktree is clean.
- `01_method_seed_table.csv`: 39 rows (13 seeds x 3 methods), byte-copy of committed combined table.
- `02_traces/per_evaluation_traces.csv`: 936 rows (39 x 24); null/inf preserved as empty cells.
- `04_curves_best_qor_vs_evals.csv`: 936 rows; 96 empty best-QoR cells (= +inf) preserved with flag.
- `03` recompute asserts: 13-seed primary tie; mean failed EDA 13046.8/14378.0/14994.8 s; paired FlowGuard-minus-EI-only dQoR=0 and dCall=0 on every seed.
- Original seeds 11/29/47 labeled via `cohort=original` in all machine-readable outputs.
- No EDA/optimizer runs launched; no RTL/primary edits; bundle assembled from existing evidence only.
- No standalone combined-13 verification log exists; separate legacy/ext10 logs and combined process snapshots are preserved.

# Authentic demo sequence (one decision, fully traceable)

- Exact command: `.venv/ml/bin/python experiments/crossbar_v2/replay_36pool_offline.py` (cache replay; 0 physical runs launched).
- Config: `designs/crossbar_datapath_v2/characterization/config-cb36-002.json` (sha256 `34a9ef3348b4…`; knobs AREA 0 / d35 / p2 / grt0.2).
- Decision record: seed 11, `flowguard_calibrated`, call 10 (adaptive), selects `cb36_002`; provenance rank 1 of 27 scored, EI 0.0 x p_feas 0.08, RF fallback `class_counts=[1, 8]`, data_hash `48dfd5aa…`, full record in `06_demo.json` and committed `replay_36pool_combined13_results.json`.
- Result checks: feasible, QoR -0.09306823743826212 (oracle-best), setup_ws +0.19090329857261953, hold_ws +0.133669412655366, wl 141422 um, area 37314.5 um2, crit 19.70909670142738 ns, DRC 0, routing 100, LVS/signoff pass, recorded runtime 607.8006902540001 s. First-to-best on this trace (call 10); EI-only also call 10; Vanilla same seed needs call 15.
- Matching layout image: `experiments/crossbar_v2/artifacts_36pool/cb36_002.png` (sha256 `35fbbd7e0a26…`).
- Separate-runs note: the image is from the earlier banked characterization physical run `trial_cb36_002` (separate run), NOT from the replay — the replay launched zero physical runs and only re-attached banked outcomes by ID.

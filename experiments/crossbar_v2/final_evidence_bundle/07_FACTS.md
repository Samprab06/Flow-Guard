# Facts sheet — confirmed values, discrepancies, sources

## Confirmed

- Oracle: 36 entries, 6 feasible (`cb36_001/002/005/006/009/010`), 2 distinct feasible QoR values (-0.09306823743826212 x3 at 002/006/010; 0.3112996180098017 x3).
- Ledger runtimes: all 36 finite; 0 null, 0 inf. `inf` exists only as 96 empty best-QoR curve cells (pre-first-feasible = +inf), preserved as empty + flag.
- Primary endpoint: final best feasible QoR ties 3-way on all 13 seeds.
- Time-to-best: FlowGuard == EI-only on all 13 seeds; both beat Vanilla by 5-6 calls on seeds 11/29/101/131; 9 seeds decided inside shared init.
- Fallback exercised only on seed 101 (`fallback_uses=2`, all methods).
- Fresh validation: `cb36_002`/`cb36_006` reruns MATCH oracle on every physical metric; runtimes +15.8/+6.8 s wall-clock variance only.
- Pilot (1337/1339/1340, 6-call, 6-cand pool) is a separate protocol; not comparable to the 36-pool replay.
- No standalone combined-13 verification log exists; legacy-9 and extension-10 verification logs are preserved, and combined JSON contains before/after zero-EDA process snapshots.

## Unresolved / must-not-overclaim discrepancies

- QoR display rounding: reports show 9dp; JSON/ledger carry full precision.
- Two runtime timings: `runtime_s` (authoritative for sums) vs coarse `launch_s`.
- Seed 47 decided by init luck (best arm in shared init, call 8).
- Vanilla collects more feasible arms (6.0 vs 4.38 vs 3.38) yet ties on best QoR — extras are QoR-duplicates.

## Source paths

See `07_FACTS.json:source_paths` for exact committed paths.

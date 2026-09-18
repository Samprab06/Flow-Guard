# crossbar_datapath_v1 physical characterization

The complete physical characterization report and immutable raw artifacts are
archived outside the repository at:

`/home/ubuntu/external-tinytapeout-work/artifacts/external_tinytapeout_compact_v1/crossbar_datapath_v1_physical_v1/REPORT.md`

Summary:

- Fixed absolute footprint: `DIE_AREA=[0,0,320,200]` (2x2 equivalent).
- Wide-port blocker: 264 top-level port bits make this a direct-core physical
  benchmark, not a TinyTapeout pad-compatible wrapper.
- LibreLane 3.0.14 / SKY130A pinned revision; baseline completed all checks.
- Baseline: area `34191.5 um2`, setup WS `-2.544121 ns`, hold WS `+0.133575 ns`,
  routing `100%`, DRC/LVS/signoff pass.
- Characterization: 8 legal configurations after baseline; 4 complete and 4
  routing-timeout/aborted. Complete-run setup WS range is `-2.544121..-0.581220`
  ns, so feasible count is zero.
- Useful sensitivity is present, but the go/no-go is **NO-GO** for production
  hardening or FlowGuard optimization until timing closure/footprint refinement.

FIR and stress sources remain untouched. No FlowGuard optimization campaign was
launched.

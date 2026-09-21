# Final evidence bundle — manifest

- git commit: `68ab3f371a4edb72c752f57983ff7d007b2c5e0f` (working tree clean at assembly: NO — see 00_MANIFEST.json)
- Scope: existing committed/local artifacts only. No EDA or optimizer runs launched; no RTL/primary-file edits; nothing committed.
- Frozen config: RTL `designs/crossbar_datapath_v2/src/crossbar_datapath_v2.sv` (sha256 `e2848bb4…5407d37`), clock 19.9 ns, die 320x200, FP_CORE_UTIL 30.
- Environment: LibreLane 3.0.14, image `ghcr.io/librelane/librelane@sha256:f91b21d7…8280a30f`, PDK sky130A rev `8afc8346…78e71`, SCL sky130_fd_sc_hd (source: `environment/openlane-baseline.env`).
- Objective `qor_v1_crossbar_v2` (`src/primary_loop.py:compute_qor`): `0.5*(crit-min)/(max-min) + 0.3*(wl-min)/(max-min) + 0.2*(area-min)/(max-min)`, weights crit 0.5 / wl 0.3 / area 0.2; baselines min/max over the 6-candidate pilot pool (crit 19.891500132283074/21.398575528307965 ns, wl 145247/152234 um, area 36947.9/37504.7 um2).
- Feasibility (`src/parser.py:is_feasible`): SUCCESS/FEASIBLE + DRC==0 + setup_ws>=0 + hold_ws>=0 + hold_vio==0 + routing==100 + overflow==0/null + LVS + signoff + missing==[].
- Primary endpoint: final best feasible QoR under equal 24-call budgets — 3-way tie on all 13 seeds (no evidence of general optimizer superiority).
- Runtime sums are estimated sequential evaluation costs from recorded physical runs; optimizer overhead is listed separately.

# crossbar_datapath_v2

Isolated follow-on to the verified `crossbar_datapath_v1` benchmark. The v1
source (`designs/crossbar_datapath_v1/`) is untouched; v2 is a self-contained
duplicate of the v1 datapath plus exactly **one** clean pipeline stage.

The parameterized `crossbar_datapath_v2` module defaults to `REG_COUNT=8`,
`LANES=4`, and `DATA_WIDTH=16`, with the same port list, ALU encodings (`ADD`
`00`, `SUB` `01`, `AND` `10`, `XOR` `11`), one-writeback-per-lane commit
semantics (higher lane index wins on collisions), active-high synchronous
reset, and `init_*` seeding port as v1.

## Pipeline boundary / latency contract

- Boundary: combinational `alu_result` -> `lane_result_q[LANES]` registers ->
  `lane_result`. A single `always_ff @(posedge clk)` stage; no other
  sequential state was added.
- `lane_result`: **exactly 1-cycle latency vs v1**. Inputs sampled on cycle N
  appear on `lane_result` after the cycle-N rising edge (visible cycle N+1).
- `reg_state`: **0-cycle latency** (unchanged combinational readout).
- Register-file writeback: **unchanged from v1** — writeback data is the
  current-cycle combinational `alu_result` and commits on the same edge, so
  the register-file trajectory is cycle-identical to v1 under identical
  stimulus. Only `lane_result` is delayed.
- Reset: synchronous, active high; clears both the register file and the
  pipeline registers. First `lane_result` after reset deasserts is zero
  (flush), then live data with 1-cycle latency.

## Tests

v2 reuses the v1 test infrastructure pattern (icarus `iverilog`/`vvp`,
xorshift seed `0x1badf00d`): reset checks, register seeding, directed
all-ALU/all-lane coverage, an explicit 1-cycle pipeline flush check, 200
deterministic randomized cycles, and a final pipeline drain step.

```bash
python3 designs/crossbar_datapath_v2/test/test_crossbar_datapath_v2.py
```

The v1 regression remains the untouched reference:

```bash
python3 designs/crossbar_datapath_v1/test/test_crossbar_datapath.py
```

## Physical characterization and freeze

- `config.json` mirrors the v1 physical baseline footprint
  (`DIE_AREA=[0,0,320,200]`, 30% core util, 45% placement density,
  `CLOCK_PERIOD=20.0`) so a future hardening run is directly comparable.
- The corrected v2 baseline closes at 20.0 ns with setup WS `+0.0885 ns`,
  hold WS `+0.1287 ns`, zero routed DRC errors, and passing LVS/signoff.
- Characterization found a fixed mixed point at `19.9 ns`: padding 0 closes
  setup at `+0.0085 ns`, while padding 2 fails at `-0.0410 ns`. AREA 1 and
  GRT 0.2 are also infeasible at this clock. The comparison freeze is
  `19.9 ns`, `320x200 um`, `FP_CORE_UTIL=30`, with knob bounds recorded in
  `experiments/crossbar_v2/frozen_manifest.json`.
- Physical characterization and the equal-budget replay are documented in
  `experiments/crossbar_v2/CHARACTERIZATION.md` and `REPORT.md`. The v1
  characterization remains unchanged.

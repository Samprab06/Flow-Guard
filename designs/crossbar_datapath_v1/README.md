# crossbar_datapath_v1

Isolated FlowGuard-recovery benchmark. This namespace does not modify the
completed `flowguard_fir` or `flowguard_stress` designs.

The parameterized `crossbar_datapath_v1` module defaults to `REG_COUNT=8`,
`LANES=4`, and `DATA_WIDTH=16`. Every lane selects two register-file entries
through independent crossbars and performs `ADD` (`00`), `SUB` (`01`), `AND`
(`10`), or `XOR` (`11`). `wb_en` and `wb_addr` provide one writeback per lane;
all enabled writebacks commit on the same rising clock edge. If destinations
collide, higher lane index wins (lane 3 has highest priority). `rst` is an
active-high synchronous reset. The auxiliary `init_*` port seeds registers for
simulation and later integration experiments.

The physical baseline uses a fixed 2x2-footprint equivalent
(`DIE_AREA=[0,0,320,200]`) at 30% core utilization and 45% placement target
density. This is a wide-port benchmark rather than a TinyTapeout pad wrapper;
the physical experiment therefore hardens the core directly and retains the
wide-port limitation in its report.

Run the short RTL-only regression before any physical-design command:

```bash
python3 designs/crossbar_datapath_v1/test/test_crossbar_datapath.py
```

The SystemVerilog testbench uses a fixed xorshift seed and 200 randomized
cycles, in addition to reset, register seeding, and directed operation tests.

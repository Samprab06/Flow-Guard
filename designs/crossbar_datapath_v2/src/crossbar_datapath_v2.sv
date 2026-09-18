`timescale 1ns/1ps
`default_nettype none

// Isolated follow-on benchmark derived from the verified crossbar_datapath_v1
// RTL (designs/crossbar_datapath_v1/src/crossbar_datapath_v1.sv, untouched).
// Change vs v1: exactly ONE clean pipeline stage registers the per-lane ALU
// results at the `lane_result` output boundary.  Nothing else is altered:
// the register file, crossbar selectors, ALU encodings, writeback priority,
// synchronous reset semantics, and `reg_state` combinational readout are
// bit-identical to v1.
//
// Pipeline boundary / latency contract:
//   * Stage boundary: combinational `alu_result` -> `lane_result_q` registers
//     -> `lane_result` outputs.  One `always_ff @(posedge clk)` block holds
//     the entire stage; no other sequential state was added.
//   * `lane_result` latency: exactly 1 clock cycle vs v1.  Inputs sampled on
//     cycle N (against the register file as it stands in cycle N) appear on
//     `lane_result` after the cycle-N rising edge (visible in cycle N+1).
//   * `reg_state` latency: 0 cycles (unchanged, combinational readout).
//   * Register-file writeback path: unchanged from v1.  Writeback data is the
//     combinational `alu_result` of the current cycle and commits on the same
//     rising edge, so the register-file trajectory is cycle-identical to v1
//     under identical stimulus.  Only `lane_result` is delayed.
//   * Reset: active-high synchronous.  On a rising edge with `rst==1`, both
//     the register file and the pipeline registers clear to zero.  The first
//     `lane_result` after reset deasserts is zero (pipeline flush), then live
//     data flows with 1-cycle latency.
module crossbar_datapath_v2 #(
    parameter integer REG_COUNT  = 8,
    parameter integer LANES      = 4,
    parameter integer DATA_WIDTH = 16
) (
    input  logic                         clk,
    input  logic                         rst,

    // One auxiliary write port initializes the register file.  Lane writeback
    // ports are independent and commit together on the active clock edge.
    input  logic                         init_we,
    input  logic [(REG_COUNT <= 1 ? 1 : $clog2(REG_COUNT))-1:0] init_waddr,
    input  logic [DATA_WIDTH-1:0]        init_wdata,
    input  logic [LANES-1:0]             wb_en,
    input  logic [LANES*(REG_COUNT <= 1 ? 1 : $clog2(REG_COUNT))-1:0] wb_addr,

    // Each lane independently selects two register-file sources and one ALU op.
    // Operation encoding: 00 ADD, 01 SUB, 10 AND, 11 XOR.
    input  logic [LANES*(REG_COUNT <= 1 ? 1 : $clog2(REG_COUNT))-1:0] src_a_sel,
    input  logic [LANES*(REG_COUNT <= 1 ? 1 : $clog2(REG_COUNT))-1:0] src_b_sel,
    input  logic [LANES*2-1:0]                 lane_op,

    output logic [LANES*DATA_WIDTH-1:0]        lane_result,
    output logic [REG_COUNT*DATA_WIDTH-1:0]    reg_state
);
    localparam integer ADDR_WIDTH = (REG_COUNT <= 1) ? 1 : $clog2(REG_COUNT);

    logic [DATA_WIDTH-1:0] registers [0:REG_COUNT-1];
    logic [DATA_WIDTH-1:0] source_a [0:LANES-1];
    logic [DATA_WIDTH-1:0] source_b [0:LANES-1];
    logic [DATA_WIDTH-1:0] alu_result [0:LANES-1];
    // THE one added pipeline stage: registered ALU results feeding lane_result.
    logic [DATA_WIDTH-1:0] lane_result_q [0:LANES-1];
    integer lane;
    integer output_lane;
    integer state_reg;

    // The crossbar and ALUs are combinational.  Out-of-range selectors are
    // treated as zero, making non-power-of-two parameterizations deterministic.
    // Identical to v1.
    always_comb begin
        for (lane = 0; lane < LANES; lane = lane + 1) begin
            source_a[lane] = '0;
            source_b[lane] = '0;
            alu_result[lane] = '0;

            if (src_a_sel[lane*ADDR_WIDTH +: ADDR_WIDTH] < REG_COUNT)
                source_a[lane] = registers[src_a_sel[lane*ADDR_WIDTH +: ADDR_WIDTH]];
            if (src_b_sel[lane*ADDR_WIDTH +: ADDR_WIDTH] < REG_COUNT)
                source_b[lane] = registers[src_b_sel[lane*ADDR_WIDTH +: ADDR_WIDTH]];

            case (lane_op[lane*2 +: 2])
                2'b00: alu_result[lane] = source_a[lane] + source_b[lane];
                2'b01: alu_result[lane] = source_a[lane] - source_b[lane];
                2'b10: alu_result[lane] = source_a[lane] & source_b[lane];
                2'b11: alu_result[lane] = source_a[lane] ^ source_b[lane];
                default: alu_result[lane] = '0;
            endcase
        end
    end

    // Pipeline output mux: registered only.  Identical width/order to v1.
    always_comb begin
        lane_result = '0;
        for (output_lane = 0; output_lane < LANES; output_lane = output_lane + 1)
            lane_result[output_lane*DATA_WIDTH +: DATA_WIDTH] = lane_result_q[output_lane];
    end

    always_comb begin
        reg_state = '0;
        for (state_reg = 0; state_reg < REG_COUNT; state_reg = state_reg + 1)
            reg_state[state_reg*DATA_WIDTH +: DATA_WIDTH] = registers[state_reg];
    end

    // Reset is synchronous and active high.  Initialization is applied first;
    // if destinations collide, lane 3 has the highest deterministic priority.
    // Writeback commits the COMBINATIONAL alu_result (v1 semantics); the
    // pipeline register independently captures it for next-cycle lane_result.
    integer write_lane;
    always_ff @(posedge clk) begin
        if (rst) begin
            for (write_lane = 0; write_lane < REG_COUNT; write_lane = write_lane + 1)
                registers[write_lane] <= '0;
            for (write_lane = 0; write_lane < LANES; write_lane = write_lane + 1)
                lane_result_q[write_lane] <= '0;
        end else begin
            if (init_we && (init_waddr < REG_COUNT))
                registers[init_waddr] <= init_wdata;
            for (write_lane = 0; write_lane < LANES; write_lane = write_lane + 1) begin
                if (wb_en[write_lane] &&
                    (wb_addr[write_lane*ADDR_WIDTH +: ADDR_WIDTH] < REG_COUNT))
                    registers[wb_addr[write_lane*ADDR_WIDTH +: ADDR_WIDTH]] <=
                        alu_result[write_lane];
            end
            for (write_lane = 0; write_lane < LANES; write_lane = write_lane + 1)
                lane_result_q[write_lane] <= alu_result[write_lane];
        end
    end
endmodule

`default_nettype wire

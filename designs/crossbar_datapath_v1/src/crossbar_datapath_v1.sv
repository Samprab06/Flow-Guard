`timescale 1ns/1ps
`default_nettype none

// Isolated FlowGuard recovery benchmark: register-file crossbar and ALU lanes.
module crossbar_datapath_v1 #(
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
    integer lane;
    integer reg_index;

    // The crossbar and ALUs are combinational.  Out-of-range selectors are
    // treated as zero, making non-power-of-two parameterizations deterministic.
    always_comb begin
        lane_result = '0;
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

            lane_result[lane*DATA_WIDTH +: DATA_WIDTH] = alu_result[lane];
        end
    end

    always_comb begin
        reg_state = '0;
        for (reg_index = 0; reg_index < REG_COUNT; reg_index = reg_index + 1)
            reg_state[reg_index*DATA_WIDTH +: DATA_WIDTH] = registers[reg_index];
    end

    // Reset is synchronous and active high.  Initialization is applied first;
    // if destinations collide, lane 3 has the highest deterministic priority.
    integer write_lane;
    always_ff @(posedge clk) begin
        if (rst) begin
            for (write_lane = 0; write_lane < REG_COUNT; write_lane = write_lane + 1)
                registers[write_lane] <= '0;
        end else begin
            if (init_we && (init_waddr < REG_COUNT))
                registers[init_waddr] <= init_wdata;
            for (write_lane = 0; write_lane < LANES; write_lane = write_lane + 1) begin
                if (wb_en[write_lane] &&
                    (wb_addr[write_lane*ADDR_WIDTH +: ADDR_WIDTH] < REG_COUNT))
                    registers[wb_addr[write_lane*ADDR_WIDTH +: ADDR_WIDTH]] <=
                        alu_result[write_lane];
            end
        end
    end
endmodule

`default_nettype wire

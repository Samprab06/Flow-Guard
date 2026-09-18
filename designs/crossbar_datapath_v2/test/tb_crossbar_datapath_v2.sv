`timescale 1ns/1ps

// Functional testbench for crossbar_datapath_v2.  Derived from the v1
// testbench (designs/crossbar_datapath_v1/test/tb_crossbar_datapath_v1.sv,
// untouched) with exactly one modeling change: `lane_result` is expected one
// clock cycle later than in v1, matching the single output pipeline stage.
// Register-file behavior (`reg_state`, writeback commits) is expected
// cycle-identical to v1.  Stimulus (reset sequence, seeding, directed ALU
// coverage, 200 deterministic xorshift-randomized cycles with seed
// 32'h1badf00d) is unchanged.
module crossbar_datapath_v2_tb;
    localparam integer REG_COUNT = 8;
    localparam integer LANES = 4;
    localparam integer DATA_WIDTH = 16;
    localparam integer ADDR_WIDTH = 3;

    logic clk;
    logic rst;
    logic init_we;
    logic [ADDR_WIDTH-1:0] init_waddr;
    logic [DATA_WIDTH-1:0] init_wdata;
    logic [LANES-1:0] wb_en;
    logic [LANES*ADDR_WIDTH-1:0] wb_addr;
    logic [LANES*ADDR_WIDTH-1:0] src_a_sel;
    logic [LANES*ADDR_WIDTH-1:0] src_b_sel;
    logic [LANES*2-1:0] lane_op;
    logic [LANES*DATA_WIDTH-1:0] lane_result;
    logic [REG_COUNT*DATA_WIDTH-1:0] reg_state;

    logic [DATA_WIDTH-1:0] model_regs [0:REG_COUNT-1];
    logic [DATA_WIDTH-1:0] expected_results [0:LANES-1];
    // Combinational result of the PREVIOUS cycle: what the v2 output pipeline
    // register must present on lane_result during the current cycle.
    logic [DATA_WIDTH-1:0] expected_prev [0:LANES-1];
    integer lane;
    integer index;
    integer cycle;
    reg [31:0] random_state;
    reg [DATA_WIDTH-1:0] a_value;
    reg [DATA_WIDTH-1:0] b_value;

    crossbar_datapath_v2 #(
        .REG_COUNT(REG_COUNT), .LANES(LANES), .DATA_WIDTH(DATA_WIDTH)
    ) dut (
        .clk(clk), .rst(rst), .init_we(init_we), .init_waddr(init_waddr),
        .init_wdata(init_wdata), .wb_en(wb_en), .wb_addr(wb_addr),
        .src_a_sel(src_a_sel), .src_b_sel(src_b_sel), .lane_op(lane_op),
        .lane_result(lane_result), .reg_state(reg_state)
    );

    always #5 clk = ~clk;

    function [31:0] next_random(input [31:0] value);
        reg [31:0] x;
        begin
            x = value;
            x = x ^ (x << 13);
            x = x ^ (x >> 17);
            x = x ^ (x << 5);
            next_random = x;
        end
    endfunction

    // Combinational expectation for the CURRENT inputs against the model file.
    task compute_expected;
        begin
            for (lane = 0; lane < LANES; lane = lane + 1) begin
                a_value = model_regs[src_a_sel[lane*ADDR_WIDTH +: ADDR_WIDTH]];
                b_value = model_regs[src_b_sel[lane*ADDR_WIDTH +: ADDR_WIDTH]];
                case (lane_op[lane*2 +: 2])
                    2'b00: expected_results[lane] = a_value + b_value;
                    2'b01: expected_results[lane] = a_value - b_value;
                    2'b10: expected_results[lane] = a_value & b_value;
                    2'b11: expected_results[lane] = a_value ^ b_value;
                endcase
            end
        end
    endtask

    // v2 check: lane_result must equal the PREVIOUS cycle's combinational
    // result (the contents of the output pipeline register).
    task check_lane_results_pipelined;
        begin
            for (lane = 0; lane < LANES; lane = lane + 1) begin
                if (lane_result[lane*DATA_WIDTH +: DATA_WIDTH] !== expected_prev[lane]) begin
                    $display("lane mismatch cycle=%0d lane=%0d got=%h expected(prev)=%h",
                             cycle, lane, lane_result[lane*DATA_WIDTH +: DATA_WIDTH],
                             expected_prev[lane]);
                    $fatal(1);
                end
            end
        end
    endtask

    task check_register_state;
        begin
            for (index = 0; index < REG_COUNT; index = index + 1) begin
                if (reg_state[index*DATA_WIDTH +: DATA_WIDTH] !== model_regs[index]) begin
                    $display("register mismatch cycle=%0d register=%0d got=%h expected=%h",
                             cycle, index, reg_state[index*DATA_WIDTH +: DATA_WIDTH],
                             model_regs[index]);
                    $fatal(1);
                end
            end
        end
    endtask

    task model_and_step;
        begin
            #1;
            compute_expected;
            // Before the first reset edge, the register file is intentionally
            // uninitialized; synchronous reset is checked after that edge.
            // lane_result is additionally expected to be flushed to zero while
            // reset is asserted (checked after the edge via expected_prev).
            if (!rst)
                check_lane_results_pipelined;
            @(posedge clk);
            #1;
            if (rst) begin
                for (index = 0; index < REG_COUNT; index = index + 1)
                    model_regs[index] = '0;
                for (lane = 0; lane < LANES; lane = lane + 1)
                    expected_prev[lane] = '0;
            end else begin
                if (init_we)
                    model_regs[init_waddr] = init_wdata;
                // Match the RTL's ordered nonblocking assignments on collisions.
                // Writeback uses the CURRENT combinational result (v1 semantics).
                for (lane = 0; lane < LANES; lane = lane + 1)
                    if (wb_en[lane])
                        model_regs[wb_addr[lane*ADDR_WIDTH +: ADDR_WIDTH]] = expected_results[lane];
                // The output pipeline stage captures the current result.
                for (lane = 0; lane < LANES; lane = lane + 1)
                    expected_prev[lane] = expected_results[lane];
            end
            check_register_state;
        end
    endtask

    initial begin
        clk = 1'b0;
        rst = 1'b1;
        init_we = 1'b0;
        init_waddr = '0;
        init_wdata = '0;
        wb_en = '0;
        wb_addr = '0;
        src_a_sel = '0;
        src_b_sel = '0;
        lane_op = '0;
        random_state = 32'h1badf00d;
        cycle = 0;
        for (index = 0; index < REG_COUNT; index = index + 1)
            model_regs[index] = '0;
        for (lane = 0; lane < LANES; lane = lane + 1)
            expected_prev[lane] = '0;

        // Synchronous reset must not clear state until a rising edge.
        model_and_step;
        model_and_step;
        rst = 1'b0;

        // Seed every register through the auxiliary write port.
        for (index = 0; index < REG_COUNT; index = index + 1) begin
            init_we = 1'b1;
            init_waddr = index[ADDR_WIDTH-1:0];
            init_wdata = 16'h1000 + index;
            wb_en = '0;
            model_and_step;
            cycle = cycle + 1;
        end
        init_we = 1'b0;

        // Directed coverage of all four ALU operations and four simultaneous writes.
        src_a_sel = {3'd6, 3'd4, 3'd2, 3'd0};
        src_b_sel = {3'd7, 3'd5, 3'd3, 3'd1};
        lane_op = {2'b11, 2'b10, 2'b01, 2'b00};
        wb_addr = {3'd3, 3'd2, 3'd1, 3'd0};
        wb_en = 4'b1111;
        model_and_step;
        cycle = cycle + 1;

        // Pipeline flush check: the directed-cycle results must appear on
        // lane_result exactly one cycle later (checked implicitly by the next
        // model_and_step's pipelined comparison), plus one explicit drain step
        // with held inputs before randomized traffic begins.
        model_and_step;
        cycle = cycle + 1;

        // Deterministic randomized crossbar, operation, and writeback traffic.
        for (cycle = 0; cycle < 200; cycle = cycle + 1) begin
            random_state = next_random(random_state);
            init_we = random_state[0];
            init_waddr = random_state[3:1];
            init_wdata = random_state[31:16];
            for (lane = 0; lane < LANES; lane = lane + 1) begin
                random_state = next_random(random_state);
                src_a_sel[lane*ADDR_WIDTH +: ADDR_WIDTH] = random_state[2:0];
                random_state = next_random(random_state);
                src_b_sel[lane*ADDR_WIDTH +: ADDR_WIDTH] = random_state[2:0];
                lane_op[lane*2 +: 2] = random_state[4:3];
                wb_addr[lane*ADDR_WIDTH +: ADDR_WIDTH] = random_state[7:5];
                wb_en[lane] = random_state[8];
            end
            model_and_step;
        end

        // Drain: hold final inputs one extra cycle so the last randomized
        // result is observed through the 1-cycle pipeline before PASS.
        wb_en = '0;
        init_we = 1'b0;
        model_and_step;

        $display("PASS: reset, seeded register file, all ALUs, crossbar, 1-stage pipeline, and 200 randomized cycles");
        $finish;
    end
endmodule

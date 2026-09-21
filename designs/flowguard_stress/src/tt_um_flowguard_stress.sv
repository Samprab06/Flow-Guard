`timescale 1ns/1ps
`default_nettype none
/* verilator lint_off DECLFILENAME */
/* verilator lint_off PINCONNECTEMPTY */

// Four-bit carry-lookahead slice.  cla20 chains five slices, keeping the
// carry equations explicit rather than relying on an inferred wide adder.
module flowguard_cla4 (
    input  logic [3:0] a,
    input  logic [3:0] b,
    input  logic       cin,
    output logic [3:0] sum,
    output logic       cout
);
    logic [3:0] p;
    logic [3:0] g;
    logic c1, c2, c3;

    assign p = a ^ b;
    assign g = a & b;
    assign c1 = g[0] | (p[0] & cin);
    assign c2 = g[1] | (p[1] & g[0]) | (p[1] & p[0] & cin);
    assign c3 = g[2] | (p[2] & g[1]) | (p[2] & p[1] & g[0]) |
                (p[2] & p[1] & p[0] & cin);
    assign cout = g[3] | (p[3] & g[2]) | (p[3] & p[2] & g[1]) |
                  (p[3] & p[2] & p[1] & g[0]) |
                  (p[3] & p[2] & p[1] & p[0] & cin);
    assign sum = {p[3] ^ c3, p[2] ^ c2, p[1] ^ c1, p[0] ^ cin};
endmodule

module flowguard_cla20 (
    input  logic signed [19:0] a,
    input  logic signed [19:0] b,
    output logic signed [19:0] sum
);
    logic c4, c8, c12, c16;

    flowguard_cla4 add0 (.a(a[3:0]),   .b(b[3:0]),   .cin(1'b0), .sum(sum[3:0]),   .cout(c4));
    flowguard_cla4 add1 (.a(a[7:4]),   .b(b[7:4]),   .cin(c4),   .sum(sum[7:4]),   .cout(c8));
    flowguard_cla4 add2 (.a(a[11:8]),  .b(b[11:8]),  .cin(c8),   .sum(sum[11:8]),  .cout(c12));
    flowguard_cla4 add3 (.a(a[15:12]), .b(b[15:12]), .cin(c12),  .sum(sum[15:12]), .cout(c16));
    flowguard_cla4 add4 (.a(a[19:16]), .b(b[19:16]), .cin(c16),  .sum(sum[19:16]), .cout());
endmodule

// Stress-oriented sensor MAC.
//
// Design intent: retain explicit eight-byte state/window and coefficient
// storage while folding the MAC through one signed 8x8 multiplier.  Each tap
// traverses a registered four-stage CLA pipeline before updating the running
// sum. This remains a substantial arithmetic/control workload without the
// eight parallel multipliers of the earlier stress implementation. No cell
// count is asserted here because it depends on the synthesis flow/library.
//
// ui_in: signed sensor sample (or signed coefficient value while loading).
// uio_in[0]: sample_valid; uio_in[1]: coefficient_load;
// uio_in[4:2]: coefficient index.  Coefficients reset to [1..8].
// uo_out: low eight bits of the signed 20-bit completed MAC.
module tt_um_flowguard_stress (
    input  logic [7:0] ui_in,
    output logic [7:0] uo_out,
    input  logic [7:0] uio_in,
    output logic [7:0] uio_out,
    output logic [7:0] uio_oe,
    input  logic       ena,
    input  logic       clk,
    input  logic       rst_n
);
    logic signed [7:0] window0, window1, window2, window3;
    logic signed [7:0] window4, window5, window6, window7;
    logic signed [7:0] coeff0, coeff1, coeff2, coeff3;
    logic signed [7:0] coeff4, coeff5, coeff6, coeff7;
    logic signed [7:0] snapshot0, snapshot1, snapshot2, snapshot3;
    logic signed [7:0] snapshot4, snapshot5, snapshot6, snapshot7;
    logic signed [15:0] product_reg;
    logic signed [19:0] accumulator;
    logic signed [19:0] stage0, stage1, stage2, stage3;
    logic signed [19:0] mac_result;
    logic [7:0] sample_count;
    logic [2:0] tap_index;
    logic [2:0] phase;
    logic mac_busy, mac_valid;

    wire sample_accept = ena && uio_in[0] && !uio_in[1] && !mac_busy;
    wire coeff_accept = ena && uio_in[1] && !mac_busy;
    wire signed [7:0] sensor_sample = ui_in;
    wire signed [19:0] product_ext = {{4{product_reg[15]}}, product_reg};
    logic signed [19:0] stage0_next, stage1_next, stage2_next, stage3_next;

    function automatic logic signed [7:0] select_snapshot(input logic [2:0] index);
        begin
            case (index)
                3'd0: select_snapshot = snapshot0; 3'd1: select_snapshot = snapshot1;
                3'd2: select_snapshot = snapshot2; 3'd3: select_snapshot = snapshot3;
                3'd4: select_snapshot = snapshot4; 3'd5: select_snapshot = snapshot5;
                3'd6: select_snapshot = snapshot6; default: select_snapshot = snapshot7;
            endcase
        end
    endfunction

    function automatic logic signed [7:0] select_coefficient(input logic [2:0] index);
        begin
            case (index)
                3'd0: select_coefficient = coeff0; 3'd1: select_coefficient = coeff1;
                3'd2: select_coefficient = coeff2; 3'd3: select_coefficient = coeff3;
                3'd4: select_coefficient = coeff4; 3'd5: select_coefficient = coeff5;
                3'd6: select_coefficient = coeff6; default: select_coefficient = coeff7;
            endcase
        end
    endfunction

    flowguard_cla20 add_stage0 (.a(accumulator), .b(product_ext), .sum(stage0_next));
    flowguard_cla20 add_stage1 (.a(stage0), .b(20'sd0), .sum(stage1_next));
    flowguard_cla20 add_stage2 (.a(stage1), .b(20'sd0), .sum(stage2_next));
    flowguard_cla20 add_stage3 (.a(stage2), .b(20'sd0), .sum(stage3_next));

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            window0 <= '0; window1 <= '0; window2 <= '0; window3 <= '0;
            window4 <= '0; window5 <= '0; window6 <= '0; window7 <= '0;
            coeff0 <= 8'sd1; coeff1 <= 8'sd2; coeff2 <= 8'sd3; coeff3 <= 8'sd4;
            coeff4 <= 8'sd5; coeff5 <= 8'sd6; coeff6 <= 8'sd7; coeff7 <= 8'sd8;
            snapshot0 <= '0; snapshot1 <= '0; snapshot2 <= '0; snapshot3 <= '0;
            snapshot4 <= '0; snapshot5 <= '0; snapshot6 <= '0; snapshot7 <= '0;
            product_reg <= '0; accumulator <= '0;
            stage0 <= '0; stage1 <= '0; stage2 <= '0; stage3 <= '0; mac_result <= '0;
            sample_count <= '0;
            tap_index <= '0; phase <= '0; mac_busy <= 1'b0; mac_valid <= 1'b0;
        end else begin
            mac_valid <= 1'b0;

            if (coeff_accept) begin
                case (uio_in[4:2])
                    3'd0: coeff0 <= sensor_sample; 3'd1: coeff1 <= sensor_sample;
                    3'd2: coeff2 <= sensor_sample; 3'd3: coeff3 <= sensor_sample;
                    3'd4: coeff4 <= sensor_sample; 3'd5: coeff5 <= sensor_sample;
                    3'd6: coeff6 <= sensor_sample; default: coeff7 <= sensor_sample;
                endcase
            end
            if (sample_accept) begin
                // Snapshot the old window: this preserves the original MAC
                // definition while allowing the input window to shift now.
                snapshot0 <= window0; snapshot1 <= window1; snapshot2 <= window2; snapshot3 <= window3;
                snapshot4 <= window4; snapshot5 <= window5; snapshot6 <= window6; snapshot7 <= window7;
                window7 <= window6; window6 <= window5; window5 <= window4; window4 <= window3;
                window3 <= window2; window2 <= window1; window1 <= window0; window0 <= sensor_sample;
                sample_count <= sample_count + 8'd1;
                accumulator <= '0;
                tap_index <= '0;
                phase <= '0;
                mac_busy <= 1'b1;
            end else if (mac_busy) begin
                case (phase)
                    3'd0: begin
                        product_reg <= select_snapshot(tap_index) * select_coefficient(tap_index);
                        phase <= 3'd1;
                    end
                    3'd1: begin stage0 <= stage0_next; phase <= 3'd2; end
                    3'd2: begin stage1 <= stage1_next; phase <= 3'd3; end
                    3'd3: begin stage2 <= stage2_next; phase <= 3'd4; end
                    3'd4: begin
                        stage3 <= stage3_next;
                        phase <= 3'd5;
                    end
                    default: begin
                        accumulator <= stage3;
                        if (tap_index == 3'd7) begin
                            mac_result <= stage3;
                            mac_valid <= 1'b1;
                            mac_busy <= 1'b0;
                            phase <= '0;
                        end else begin
                            tap_index <= tap_index + 3'd1;
                            phase <= '0;
                        end
                    end
                endcase
            end
        end
    end

    assign uo_out = mac_result[7:0];
    // uio pins are inputs by contract; consume reserved upper bits so lint
    // reports remain clean while preserving their externally inactive value.
    assign uio_out = {8{1'b0 & ^uio_in[7:5]}};
    assign uio_oe = 8'b0;
endmodule

`default_nettype wire

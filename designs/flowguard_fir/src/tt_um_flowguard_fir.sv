`timescale 1ns/1ps
`default_nettype none

module tt_um_flowguard_fir (
    input  logic [7:0] ui_in,
    output logic [7:0] uo_out,
    input  logic [7:0] uio_in,
    output logic [7:0] uio_out,
    output logic [7:0] uio_oe,
    input  logic       ena,
    input  logic       clk,
    input  logic       rst_n
);
    logic signed [7:0] samples [0:6];
    logic signed [18:0] fir_sum;
    logic signed [18:0] sample_in_ext;
    logic signed [18:0] sample_ext [0:6];
    logic signed [7:0] output_sample;
    logic valid_output;
    integer i;

    assign sample_in_ext = {{11{ui_in[7]}}, ui_in};
    generate
        genvar j;
        for (j = 0; j < 7; j = j + 1) begin : gen_sample_extensions
            assign sample_ext[j] = {{11{samples[j][7]}}, samples[j]};
        end
    endgenerate

    // h = [1, 2, 4, 8, 8, 4, 2, 1] / 32.  Every term is a signed shift,
    // eliminating coefficient storage, writes, and general multiplication.
    assign fir_sum = sample_in_ext + (sample_ext[0] <<< 1) +
                     (sample_ext[1] <<< 2) + (sample_ext[2] <<< 3) +
                     (sample_ext[3] <<< 3) + (sample_ext[4] <<< 2) +
                     (sample_ext[5] <<< 1) + sample_ext[6];

    function automatic logic signed [7:0] saturate8(input logic signed [18:0] value);
        begin
            if (value > 19'sd127) saturate8 = 8'sd127;
            else if (value < -19'sd128) saturate8 = -8'sd128;
            else saturate8 = value[7:0];
        end
    endfunction

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < 7; i = i + 1) samples[i] <= 8'sd0;
            output_sample <= 8'sd0;
            valid_output <= 1'b0;
        end else if (ena) begin
            for (i = 6; i > 0; i = i - 1) samples[i] <= samples[i-1];
            samples[0] <= $signed(ui_in);
            output_sample <= saturate8(fir_sum >>> 5);
            valid_output <= 1'b1;
        end else begin
            valid_output <= 1'b0;
        end
    end

    assign uo_out = output_sample;
    assign uio_out = {7'b0, valid_output};
    assign uio_oe = 8'b00000001;
endmodule

`default_nettype wire

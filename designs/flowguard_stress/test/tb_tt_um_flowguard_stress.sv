`timescale 1ns/1ps
`default_nettype none

module tb_tt_um_flowguard_stress;
    logic [7:0] ui_in;
    logic [7:0] uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;
    logic ena, clk, rst_n;
    integer model_window [0:7];
    integer model_coeff [0:7];
    integer i, expected;

    tt_um_flowguard_stress dut (.*);
    /* verilator lint_off BLKSEQ */
    always #5 clk = ~clk;
    /* verilator lint_on BLKSEQ */

    function automatic integer dot_product;
        integer k;
        begin
            dot_product = 0;
            for (k = 0; k < 8; k = k + 1) dot_product = dot_product + model_window[k] * model_coeff[k];
        end
    endfunction

    task automatic load_coeff(input logic [2:0] index, input integer value);
        begin
            @(negedge clk);
            ui_in = value[7:0];
            uio_in = {3'b000, index[2:0], 2'b10};
            @(posedge clk);
            #1;
            uio_in = '0;
            model_coeff[index] = value;
        end
    endtask

    task automatic sample(input integer value);
        integer k;
        begin
            @(negedge clk);
            ui_in = value[7:0];
            uio_in = 8'h01;
            expected = dot_product();
            @(posedge clk);
            #1;
            for (k = 7; k > 0; k = k - 1) model_window[k] = model_window[k-1];
            model_window[0] = value;
            uio_in = '0;
            // One folded product crosses four registered CLA stages. Eight
            // taps therefore complete exactly 48 clocks after acceptance.
            for (k = 1; k <= 48; k = k + 1) begin
                @(posedge clk);
                #1;
                if (k < 48 && dut.mac_valid) $fatal(1, "MAC valid asserted early at cycle %0d", k);
            end
            if (!dut.mac_valid) $fatal(1, "MAC valid missing");
            if ($signed(dut.mac_result) !== $signed(expected[19:0])) $fatal(1, "MAC mismatch: got %0d expected %0d", $signed(dut.mac_result), expected);
            if (uo_out !== expected[7:0]) $fatal(1, "Output byte mismatch");
        end
    endtask

    initial begin
        clk = 0; rst_n = 0; ena = 0; ui_in = 0; uio_in = 0;
        for (i = 0; i < 8; i = i + 1) begin model_window[i] = 0; model_coeff[i] = i + 1; end
        repeat (2) @(posedge clk);
        rst_n = 1; ena = 1;
        load_coeff(0, 3); load_coeff(1, -2); load_coeff(2, 5); load_coeff(3, -4);
        load_coeff(4, 7); load_coeff(5, -6); load_coeff(6, 2); load_coeff(7, -1);
        sample(12); sample(-9); sample(33); sample(7); sample(-18); sample(45); sample(-31); sample(6);
        sample(21); sample(-12); sample(4); sample(19);
        if (uio_out !== 8'b0 || uio_oe !== 8'b0) $fatal(1, "Unexpected uio drive");
        $display("PASS: four-stage sensor MAC pipeline verified");
        $finish;
    end
endmodule

`default_nettype wire

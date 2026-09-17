`timescale 1ns/1ps

module tb_tt_um_flowguard_fir;
    reg [7:0] ui_in, uio_in;
    wire [7:0] uo_out, uio_out, uio_oe;
    reg ena, clk, rst_n;
    integer history [0:6];
    integer enabled_cycle, expected, errors, i, acc;

    tt_um_flowguard_fir dut (
        .ui_in(ui_in), .uo_out(uo_out), .uio_in(uio_in),
        .uio_out(uio_out), .uio_oe(uio_oe), .ena(ena), .clk(clk), .rst_n(rst_n)
    );

    always #5 clk = ~clk;

    function integer signed8;
        input [7:0] bits;
        begin signed8 = $signed(bits); end
    endfunction

    function integer sat8;
        input integer value;
        begin
            if (value > 127) sat8 = 127;
            else if (value < -128) sat8 = -128;
            else sat8 = value;
        end
    endfunction

    always @(posedge clk) begin
        #1;
        if (!rst_n) begin
            enabled_cycle = 0;
        end else if (ena) begin
            enabled_cycle = enabled_cycle + 1;
            acc = signed8(ui_in) + 2 * history[0] + 4 * history[1] +
                  8 * history[2] + 8 * history[3] + 4 * history[4] +
                  2 * history[5] + history[6];
            expected = sat8(acc >>> 5);
            if (!uio_out[0]) begin
                $display("FAIL missing valid at enabled cycle %0d", enabled_cycle);
                errors = errors + 1;
            end else if (signed8(uo_out) !== expected) begin
                $display("FAIL enabled cycle %0d got %0d expected %0d", enabled_cycle,
                         signed8(uo_out), expected);
                errors = errors + 1;
            end
            for (i = 6; i > 0; i = i - 1) history[i] = history[i-1];
            history[0] = signed8(ui_in);
        end else if (uio_out[0] !== 0) begin
            $display("FAIL valid asserted while ena is low");
            errors = errors + 1;
        end
    end

    task drive_sample;
        input integer value;
        input [7:0] sideband;
        begin
            @(negedge clk);
            ena = 1'b1; ui_in = value[7:0]; uio_in = sideband;
            @(posedge clk);
        end
    endtask

    initial begin
        clk = 0; ena = 0; rst_n = 0; ui_in = 0; uio_in = 0;
        enabled_cycle = 0; expected = 0; errors = 0;
        for (i = 0; i < 7; i = i + 1) history[i] = 0;
        repeat (2) @(posedge clk);
        #1;
        if (uio_out[0] !== 0 || uio_oe !== 8'b00000001 || signed8(uo_out) !== 0) begin
            $display("FAIL reset outputs"); errors = errors + 1;
        end
        @(negedge clk); rst_n = 1;

        // The fixed symmetric impulse response is [1,2,4,8,8,4,2,1]/32.
        drive_sample(127, 8'b0);
        repeat (7) drive_sample(0, 8'b0);

        // Signed arithmetic and fixed sideband behavior: uio_in cannot write taps.
        drive_sample(-128, 8'hff);
        repeat (7) drive_sample(0, 8'h80);

        // Full-scale steady-state inputs exercise the normalized endpoints.
        repeat (8) drive_sample(127, 8'b0);
        repeat (8) drive_sample(-128, 8'b0);

        // ena pauses history and suppresses valid until the next accepted sample.
        @(negedge clk); ena = 0; ui_in = 8'h55; uio_in = 8'hff;
        repeat (3) @(posedge clk);
        #1;
        if (uio_out[0] !== 0) begin
            $display("FAIL ena low advanced FIR"); errors = errors + 1;
        end
        drive_sample(9, 8'b0);

        @(negedge clk); ena = 0;
        @(posedge clk);
        if (errors == 0)
            $display("PASS: fixed CSD FIR latency is one enabled clock");
        else begin
            $display("FAIL: %0d errors", errors);
            $fatal(1);
        end
        $finish;
    end
endmodule

// Functional verification TB for aes_cipher_top_reg wrapper (encryption only).
// Same oracle vectors + reset/done protocol as tb_aes_verify.v for the
// unwrapped core; DUT is the thin input-registering wrapper, so done asserts
// ~1 cycle later (~12-13 cycles after the wrapper ld pulse instead of ~12).
// Vectors: vectors.hex, one 384-bit row per test: {key, plaintext, ct}.
// Protocol (from RTL): rst is ACTIVE-LOW. Pulse ld=1 for one cycle with
// key/text_in stable; dcnt loads 0xb and decrements; done asserts for
// exactly one cycle when dcnt==1 (~11 cycles after ld deasserts).
// Vectors: vectors.hex, one 384-bit row per test: {key, plaintext, ct}.
`timescale 1ns/1ps

module tb_aes_verify;
  reg clk = 0;
  reg rst;
  reg ld;
  reg [127:0] key;
  reg [127:0] text_in;
  wire done;
  wire [127:0] text_out;

  always #5 clk = ~clk; // 10 ns functional clock (timing-agnostic)

  aes_cipher_top_reg dut (
    .clk(clk), .rst(rst), .ld(ld), .done(done),
    .key(key), .text_in(text_in), .text_out(text_out)
  );

  parameter MAXV = 64;
  reg [383:0] vec [0:MAXV-1];
  integer nvec;
  integer i, cyc, errors, proto_errors;
  reg [127:0] exp_key, exp_pt, exp_ct;
  reg [127:0] last_good_ct;
  reg [127:0] got_ct;
  integer pulse_w;
  integer waited, ok, saw_done, w;

  task wait_cycles(input integer n);
    integer k;
    begin
      for (k = 0; k < n; k = k + 1) @(posedge clk);
    end
  endtask

  // Run one encryption; returns cycles waited via waited, sets ok=0 on mismatch/timeout.
  task run_vector(input [127:0] k, input [127:0] p, input [127:0] c,
                  output integer waited, output integer ok);
    begin
      ok = 0; waited = 0;
      key = k; text_in = p;
      @(posedge clk);
      ld = 1;
      @(posedge clk);
      ld = 0;
      // done must be low immediately after ld deasserts
      #1;
      if (done !== 1'b0) begin
        $display("PROTO-FAIL: done high right after ld deassert");
        proto_errors = proto_errors + 1;
      end
      while (waited < 60 && done !== 1'b1) begin
        @(posedge clk);
        #1;
        waited = waited + 1;
      end
      if (done !== 1'b1) begin
        $display("TIMEOUT waiting done for key=%h pt=%h", k, p);
      end else begin
        // text_out is registered every cycle: capture it on the done cycle
        // BEFORE advancing (it holds unrelated round data afterwards).
        got_ct = text_out;
        // done must be exactly one cycle wide
        pulse_w = 0;
        while (done === 1'b1 && pulse_w < 4) begin
          @(posedge clk); #1; pulse_w = pulse_w + 1;
        end
        if (pulse_w !== 1) begin
          $display("PROTO-FAIL: done pulse width=%0d (want 1)", pulse_w);
          proto_errors = proto_errors + 1;
        end
        if (got_ct !== c) begin
          $display("MISMATCH key=%h pt=%h got=%h want=%h", k, p, got_ct, c);
        end else begin
          ok = 1;
        end
      end
    end
  endtask

  initial begin
    errors = 0; proto_errors = 0;
    last_good_ct = 128'h0;
    $readmemh("vectors.hex", vec);
    // count non-x rows by scanning until first all-x (vectors.hex is exact length)
    nvec = 0;
    for (i = 0; i < MAXV; i = i + 1) begin
      if (vec[i] !== 384'hx) nvec = nvec + 1;
    end
    $display("loaded %0d vectors", nvec);
    if (nvec == 0) begin
      $display("FAIL: no vectors loaded");
      $finish;
    end

    // --- reset behavior: hold active-low reset, done must be 0 after release
    rst = 0; ld = 0; key = 0; text_in = 0;
    wait_cycles(4);
    rst = 1;
    wait_cycles(2);
    #1;
    if (done !== 1'b0) begin
      $display("PROTO-FAIL: done high after reset release (no ld yet)");
      proto_errors = proto_errors + 1;
    end else $display("reset-release check: done=0 OK");

    // --- KAT + randomized vectors
    for (i = 0; i < nvec; i = i + 1) begin
      exp_key = vec[i][383:256];
      exp_pt  = vec[i][255:128];
      exp_ct  = vec[i][127:0];
      begin
        run_vector(exp_key, exp_pt, exp_ct, waited, ok);
        if (!ok) errors = errors + 1;
        else begin
          last_good_ct = exp_ct;
          if (i < 3) $display("KAT %0d PASS (key=%h ct=%h, %0d cyc)", i, exp_key, exp_ct, waited);
        end
      end
      wait_cycles(2); // gap between back-to-back ops
    end
    $display("vector phase: %0d/%0d correct", nvec - errors, nvec);

    // --- mid-operation reset must abort (no done within window, output frozen)
    exp_key = vec[0][383:256]; exp_pt = vec[0][255:128];
    key = exp_key; text_in = exp_pt;
    @(posedge clk); ld = 1; @(posedge clk); ld = 0;
    wait_cycles(3);
    rst = 0; // assert active-low reset mid-compute
    wait_cycles(2);
    rst = 1;
    wait_cycles(2);
    begin
      saw_done = 0;
      for (w = 0; w < 25; w = w + 1) begin
        @(posedge clk); #1;
        if (done === 1'b1) saw_done = 1;
      end
      if (saw_done) begin
        $display("PROTO-FAIL: done asserted after mid-op reset (op not aborted)");
        proto_errors = proto_errors + 1;
      end else $display("mid-op reset abort check: no done OK");
      // NOTE: text_out is combinationally re-registered every cycle from the
      // round datapath and is contractually valid ONLY on the done cycle, so
      // no output-freeze is asserted here; recovery below is the real check.
    end

    // --- recovery: fresh op after abort must still work
    begin
      run_vector(vec[1][383:256], vec[1][255:128], vec[1][127:0], waited, ok);
      if (!ok) begin
        $display("PROTO-FAIL: post-reset recovery op failed");
        errors = errors + 1;
      end else $display("post-reset recovery check OK");
    end

    if (errors == 0 && proto_errors == 0)
      $display("VERIFY-PASS vectors=%0d", nvec);
    else
      $display("VERIFY-FAIL errors=%0d proto_errors=%0d", errors, proto_errors);
    $finish;
  end
endmodule

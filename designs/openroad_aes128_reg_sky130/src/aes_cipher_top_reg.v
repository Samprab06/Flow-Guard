`include "timescale.v"

// Thin input-registering wrapper around upstream aes_cipher_top.
//
// Purpose: eliminate the unregistered `ld` (and `key`/`text_in`) input
// timing artifact seen in the aes128-conservative-baseline-v1 trial, where
// all 32 setup violations started at the top-level `ld` port (4 ns input
// external delay + ~21 ns buffer/comb fanout tree to 562+ flop D pins).
// Registering the inputs at the boundary makes every top-level input drive
// exactly one wrapper flop; the deep fanout becomes internal flop-to-flop,
// which already closed 20 ns in the baseline (zero flop-to-flop violations).
//
// - Upstream RTL (`aes_cipher_top` + key-expand/rcon/sbox) is untouched and
//   instantiated verbatim.
// - Same port list as `aes_cipher_top` (clk, rst active-low, ld, done,
//   key, text_in, text_out) so the existing oracle/testbench protocol
//   reuses with no change (one extra cycle of latency: done asserts ~13
//   cycles after the wrapper `ld` pulse instead of ~12).
// - `done`/`text_out` pass through: both are already registered inside the
//   core, and `text_out` remains valid ONLY on the `done` cycle.

module aes_cipher_top_reg(clk, rst, ld, done, key, text_in, text_out);
input		clk, rst;
input		ld;
output		done;
input	[127:0]	key;
input	[127:0]	text_in;
output	[127:0]	text_out;

reg		ld_q;
reg	[127:0]	key_q;
reg	[127:0]	text_in_q;
wire		done_inner;
wire	[127:0]	text_out_inner;

// Boundary registers: unconditional capture each cycle is the thinnest
// correct form. The core samples key_q/text_in_q only when ld_q pulses
// (one cycle after the wrapper ld pulse); the testbench holds key/text_in
// stable across the pulse, so no gating mux is needed.
always @(posedge clk)
	if(!rst) begin
		ld_q      <= #1 1'b0;
		key_q     <= #1 128'h0;
		text_in_q <= #1 128'h0;
	end else begin
		ld_q      <= #1 ld;
		key_q     <= #1 key;
		text_in_q <= #1 text_in;
	end

aes_cipher_top u_core(
	.clk(		clk		),
	.rst(		rst		),
	.ld(		ld_q		),
	.done(		done_inner	),
	.key(		key_q		),
	.text_in(	text_in_q	),
	.text_out(	text_out_inner	));

assign done     = done_inner;
assign text_out = text_out_inner;

endmodule

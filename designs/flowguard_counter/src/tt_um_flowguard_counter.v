// Tiny Tapeout-style synchronous counter for an OpenLane/LibreLane smoke baseline.
module tt_um_flowguard_counter (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
    reg [7:0] count;

    always @(posedge clk) begin
        if (!rst_n)
            count <= 8'h00;
        else if (ena)
            count <= count + ui_in + 8'h01;
    end

    assign uo_out = count;
    assign uio_out = 8'h00;
    assign uio_oe = 8'h00;

    wire _unused = &{1'b0, uio_in};
endmodule

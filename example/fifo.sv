module fifo #(
	parameter integer N = 8
) (
	input clock,
	input reset,

	input		WVALID,
	output		WREADY,
	input	[N-1:0]	WDATA,

	output		RVALID,
	input		RREADY,
	output	[N-1:0]	RDATA
);
	reg [N-1:0] mem [0:3];
	reg [1:0] wp, rp;

	assign WREADY = (wp + 2'd 1) != rp;
	assign RVALID = wp != rp;
	assign RDATA = mem[rp];

	always @(posedge clock) begin
		if (WVALID && WREADY) begin
			mem[wp] <= WDATA;
			wp <= wp + 2'd 1;
		end
		if (RVALID && RREADY) begin
			rp <= rp + 2'd 1;
		end
		if (reset) begin
			wp <= 0;
			rp <= 0;
		end
	end
endmodule

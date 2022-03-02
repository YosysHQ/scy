(* keep *)
module mem (
	input clock,
	input reset,

	// AXI4-Lite Write Address Channel
	input		AWVALID,
	output		AWREADY,
	input	[31:0]	AWADDR,

	// AXI4-Lite Write Data Channel
	input		WVALID,
	output		WREADY,
	input	[31:0]	WDATA,
	input	[ 3:0]	WSTRB,

	// AXI4-Lite Write Response Channel
	output		BVALID,
	input		BREADY,

	// AXI4-Lite Read Address Channel
	input		ARVALID,
	output		ARREADY,
	input	[31:0]	ARADDR,

	// AXI4-Lite Read Data Channel 
	output		RVALID,
	input		RREADY,
	output	[31:0]	RDATA
);
endmodule

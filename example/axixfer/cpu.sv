(* keep *)
module cpu (
	input clock,
	input reset,

	// AXI4-Lite Write Address Channel
	output		AWVALID,
	input		AWREADY,
	output	[31:0]	AWADDR,

	// AXI4-Lite Write Data Channel
	output		WVALID,
	input		WREADY,
	output	[31:0]	WDATA,
	output	[ 3:0]	WSTRB,

	// AXI4-Lite Write Response Channel
	input		BVALID,
	output		BREADY,

	// AXI4-Lite Read Address Channel
	output		ARVALID,
	input		ARREADY,
	output	[31:0]	ARADDR,

	// AXI4-Lite Read Data Channel 
	input		RVALID,
	output		RREADY,
	input	[31:0]	RDATA
);
endmodule

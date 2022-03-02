(* keep *)
module bus (
	input clock,
	input reset,

	// =======================================

	// CPU1 Axi4-Lite Write Address Channel
	input		CPU1_AWVALID,
	output		CPU1_AWREADY,
	input	[31:0]	CPU1_AWADDR,

	// CPU1 AXI4-Lite Write Data Channel
	input		CPU1_WVALID,
	output		CPU1_WREADY,
	input	[31:0]	CPU1_WDATA,
	input	[ 3:0]	CPU1_WSTRB,

	// CPU1 AXI4-Lite Write Response Channel
	output		CPU1_BVALID,
	input		CPU1_BREADY,

	// CPU1 AXI4-Lite Read Address Channel
	input		CPU1_ARVALID,
	output		CPU1_ARREADY,
	input	[31:0]	CPU1_ARADDR,

	// CPU1 AXI4-Lite Read Data Channel 
	output		CPU1_RVALID,
	input		CPU1_RREADY,
	output	[31:0]	CPU1_RDATA,

	// =======================================

	// CPU2 Axi4-Lite Write Address Channel
	input		CPU2_AWVALID,
	output		CPU2_AWREADY,
	input	[31:0]	CPU2_AWADDR,

	// CPU2 AXI4-Lite Write Data Channel
	input		CPU2_WVALID,
	output		CPU2_WREADY,
	input	[31:0]	CPU2_WDATA,
	input	[ 3:0]	CPU2_WSTRB,

	// CPU2 AXI4-Lite Write Response Channel
	output		CPU2_BVALID,
	input		CPU2_BREADY,

	// CPU2 AXI4-Lite Read Address Channel
	input		CPU2_ARVALID,
	output		CPU2_ARREADY,
	input	[31:0]	CPU2_ARADDR,

	// CPU2 AXI4-Lite Read Data Channel 
	output		CPU2_RVALID,
	input		CPU2_RREADY,
	output	[31:0]	CPU2_RDATA,

	// =======================================

	// Memory AXI4-Lite Write Address Channel
	output		MEM_AWVALID,
	input		MEM_AWREADY,
	output	[31:0]	MEM_AWADDR,

	// Memory AXI4-Lite Write Data Channel
	output		MEM_WVALID,
	input		MEM_WREADY,
	output	[31:0]	MEM_WDATA,
	output	[ 3:0]	MEM_WSTRB,

	// Memory AXI4-Lite Write Response Channel
	input		MEM_BVALID,
	output		MEM_BREADY,

	// Memory AXI4-Lite Read Address Channel
	output		MEM_ARVALID,
	input		MEM_ARREADY,
	output	[31:0]	MEM_ARADDR,

	// Memory AXI4-Lite Read Data Channel 
	input		MEM_RVALID,
	output		MEM_RREADY,
	input	[31:0]	MEM_RDATA
);
endmodule

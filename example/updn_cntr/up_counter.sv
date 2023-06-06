module up_counter (
	input clock,
	input reset,
	input reverse,
	output [7:0] value
);
	reg [7:0] count;

	assign value = count;

	initial begin
		count = 0;
	end

	always @(posedge clock) begin
		if (reset && reverse) begin
			count = 8'h ff;
		end else if (reset && !reverse) begin
			count = 8'h 00;
		end else if (!reset && reverse) begin
			count = count-1;
		end else /*(!reset && !reverse)*/ begin
			count = count+1;
		end
		`include "cover_stmts.vh"
	end


endmodule

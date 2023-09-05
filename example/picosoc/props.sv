module props (
	input clk,
	input resetn,
	input ser_tx
);
	localparam clkdiv = 3;

	reg [7:0] ser_byte = 0;
	reg ser_byte_valid = 0;
	reg force_reset = 1;

	reg [2:0] state = 0;
	reg [7:0] bytecnt = 0;
	reg [7:0] cnt = 0;

	always @(posedge clk) begin
		cnt <= cnt + 1;
		ser_byte_valid <= 0;
		case (state)
			0: begin
				if (ser_tx == 1) state <= 1;
			end
			1: begin
				if (ser_tx == 0) state <= 2;
				cnt <= 0;
			end
			2: begin
				case (cnt)
					(clkdiv *  3): ser_byte[0] <= ser_tx;
					(clkdiv *  5): ser_byte[1] <= ser_tx;
					(clkdiv *  7): ser_byte[2] <= ser_tx;
					(clkdiv *  9): ser_byte[3] <= ser_tx;
					(clkdiv * 11): ser_byte[4] <= ser_tx;
					(clkdiv * 13): ser_byte[5] <= ser_tx;
					(clkdiv * 15): ser_byte[6] <= ser_tx;
					(clkdiv * 17): ser_byte[7] <= ser_tx;
					(clkdiv * 19): begin
						state <= 0;
						bytecnt <= bytecnt + 1;
						ser_byte_valid <= 1;
					end
				endcase
			end
		endcase
		if (!resetn) begin
			state <= 0;
			bytecnt <= 0;
			ser_byte_valid <= 0;
			force_reset = 0;
		end
	end

	always @* begin
		if (force_reset) assume (!resetn);
		char_01: cover (resetn && bytecnt ==  1 && ser_byte_valid && ser_byte == "H");
		char_02: cover (resetn && bytecnt ==  2 && ser_byte_valid && ser_byte == "e");
		char_03: cover (resetn && bytecnt ==  3 && ser_byte_valid && ser_byte == "l");
		char_04: cover (resetn && bytecnt ==  4 && ser_byte_valid && ser_byte == "l");
		char_05: cover (resetn && bytecnt ==  5 && ser_byte_valid && ser_byte == "o");
		char_06: cover (resetn && bytecnt ==  6 && ser_byte_valid && ser_byte == " ");
		char_07: cover (resetn && bytecnt ==  7 && ser_byte_valid && ser_byte == "W");
		char_08: cover (resetn && bytecnt ==  8 && ser_byte_valid && ser_byte == "o");
		char_09: cover (resetn && bytecnt ==  9 && ser_byte_valid && ser_byte == "r");
		char_10: cover (resetn && bytecnt == 10 && ser_byte_valid && ser_byte == "l");
		char_11: cover (resetn && bytecnt == 11 && ser_byte_valid && ser_byte == "d");
	end
endmodule

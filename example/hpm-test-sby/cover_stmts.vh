wire csr_insn_valid = rvfi_valid && (rvfi_insn[6:0] == 7'b 1110011) && (rvfi_insn[13:12] != 0) && ((rvfi_insn >> 16 >> 16) == 0);
wire [11:0] csr_insn_addr = rvfi_insn[31:20];
wire csr_hpmcounter_under_test = csr_insn_addr == 12'h B03 || csr_insn_addr == 12'h B83;
wire csr_hpmevent_under_test = csr_insn_addr == 12'h 323;
wire csr_write_valid = (!rvfi_insn[13] || rvfi_insn[19:15]) && csr_insn_valid;
reg [31:0] csr_hpmcounter_shadow = 0;
reg [2:0] csr_hpmevent_written;
always @(posedge clock) begin
    cp_reset_done: cover(!reset);
    if (reset) begin
        csr_hpmcounter_shadow = 0;
        csr_hpmevent_written = 0;
    end else begin
        // No writes of CSR under test allowed
        assume (!(csr_write_valid && csr_hpmcounter_under_test));
        cp_hpmevent2: cover(csr_hpmevent_written == 2'd 2);
        cp_hpmevent3: cover(csr_hpmevent_written == 2'd 3);
        cp_hpmcounter: cover(csr_hpmevent_written && (rvfi_csr_mhpmcounter3_rdata > csr_hpmcounter_shadow));
        if (csr_write_valid && csr_hpmevent_under_test) begin
            csr_hpmcounter_shadow = rvfi_csr_mhpmcounter3_rdata;
            csr_hpmevent_written = rvfi_csr_mhpmevent3_wdata;
        end
    end
end

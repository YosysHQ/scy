wire csr_insn_valid = rvfi_valid && (rvfi_insn[6:0] == 7'b 1110011) && (rvfi_insn[13:12] != 0) && ((rvfi_insn >> 16 >> 16) == 0);
wire [11:0] csr_insn_addr = rvfi_insn[31:20];
wire csr_hpmcounter_under_test = csr_insn_addr == 12'h B03 || csr_insn_addr == 12'h B83;
wire csr_hpmevent_under_test = csr_insn_addr == 12'h 323;
wire csr_write_valid = (!rvfi_insn[13] || rvfi_insn[19:15]) && csr_insn_valid;
wire csr_read_valid = rvfi_insn[11:7] != 0 && csr_insn_valid;
(* keep *)
reg csr_hpmcounter_shadowed = 0;
(* keep *)
reg [31:0] csr_hpmcounter_shadow = 0;
(* keep *)
reg [31:0] csr_hpmevent_written = 0;
(* keep *)
reg reset_q = 0;
always @(posedge clock) begin
    cp_reset_done: cover(!reset && reset_q);
    if (reset) begin
        reset_q = 1;
        csr_hpmcounter_shadowed = 0;
        csr_hpmcounter_shadow = 0;
        csr_hpmevent_written = 0;
    end else begin
        // No writes of CSR under test allowed
        assume (!(csr_write_valid && csr_hpmcounter_under_test));
        if (csr_read_valid && csr_hpmevent_under_test) begin
            assume (!csr_write_valid);
            assume (!csr_hpmcounter_shadowed);
            assume(csr_hpmevent_written == rvfi_csr_mhpmevent3_rdata);
            cp_hpmevent2: cover(csr_hpmevent_written == 'd 2);
            cp_hpmevent3: cover(csr_hpmevent_written == 'd 3);
        end
        if (csr_read_valid && csr_hpmcounter_under_test) begin
            cp_hpmcounter: cover(csr_hpmcounter_shadowed && (rvfi_csr_mhpmcounter3_rdata > csr_hpmcounter_shadow));
            csr_hpmcounter_shadowed = 1;
            csr_hpmcounter_shadow = rvfi_csr_mhpmcounter3_rdata;
        end
        if (csr_write_valid && csr_hpmevent_under_test) begin
            csr_hpmevent_written = rvfi_csr_mhpmevent3_wdata;
        end
    end
end

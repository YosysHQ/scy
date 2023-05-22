# hpm-test example

This is an example use case and test of `scy`, utilising the RISC-V formal verification framework.
The NERV core included in `riscv-formal` is instantiated with the testbench and cover check provided
by the verification framework.  [`cover_stmts.vh`](cover_stmts.vh) provides a modified version of
`rvfi_hpm_check.sv` for testing hardware performance monitor CSRs (i.e. HPMs) through the
`rvfi_cover_check.sv` checker.  This testbench monitors `mhpmevent3` and `mhpmcounter3` and provides
a number of cover statements and assumptions to facilitate testing that a given event will allow the
counter to increment at some point.

## Requirements

The `riscv-formal` project must be in the same directory as `scy`.

```
cd scy
cd ..
git clone git@github.com:YosysHQ/riscv-formal.git riscv-formal
```

## Running the example

`scy hpm-test.scy`

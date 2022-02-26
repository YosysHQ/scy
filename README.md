# Sequence of Covers with Yosys (SCY)

SCY is a tool for creating deep formal traces, by splitting the property to
cover into smaller cover properties, which the solver will cover eagerly
in sequence.

The cover points themselves are SVA cover properties. Additional data-flow
analysis properties and SVA restrict/assume properties can be used to further
narrow the search space to certain traces.

## Example SCY Config File

The `scy` command-line tool reads a `.scy` file that describes the design to check,
and the individual steps to cover.

```
[script]
read -sv top.sv cpu.sv peripheral.sv
prep -top top

[sequence]
depth 20
engine btor btormc

cover cp_reset_done:
  commit reset

cover cp_cpu_ar_valid_ready:
  cover cp_peripheral_ar_valid_ready:
    flow cpu.axi4lite_axi_arvalid@0 peripheral.axi4lite_axi_arvalid@-1
    flow cpu.axi4lite_axi_araddr@0 peripheral.axi4lite_axi_araddr@-1
    commit

  cover cp_peripheral_r_valid_ready:
    flow peripheral.axi4lite_axi_arvalid@0 peripheral.axi4lite_axi_rvalid@-1
    flow peripheral.axi4lite_axi_araddr@0 peripheral.axi4lite_axi_rdata@-1
    commit

  cover cp_cpu_r_valid_ready:
    flow peripheral.axi4lite_axi_rvalid@0 cpu.axi4lite_axi_rvalid@-1
    flow peripheral.axi4lite_axi_rdata@0 cpu.axi4lite_axi_rdata@-1
    commit

  branch axi_ar_r

cover cp_cpu_aw_valid_ready:
  cover cp_peripheral_aw_valid_ready:
    flow cpu.axi4lite_axi_awvalid@0 peripheral.axi4lite_axi_awvalid@-1
    flow cpu.axi4lite_axi_awaddr@0 peripheral.axi4lite_axi_awaddr@-1
    commit

  cover cp_peripheral_b_valid_ready:
    flow peripheral.axi4lite_axi_awvalid@0 peripheral.axi4lite_axi_bvalid@-1
    commit

  cover cp_cpu_b_valid_ready:
    flow peripheral.axi4lite_axi_bvalid@0 cpu.axi4lite_axi_bvalid@-1
    commit

  branch axi_aw_b

cover cp_cpu_w_valid_ready:
  cover cp_peripheral_w_valid_ready:
    flow cpu.axi4lite_axi_wvalid@0 peripheral.axi4lite_axi_wvalid@-1
    flow cpu.axi4lite_axi_wdata@0 peripheral.axi4lite_axi_wdata@-1
    commit

  cover cp_peripheral_b_valid_ready:
    flow peripheral.axi4lite_axi_wvalid@0 peripheral.axi4lite_axi_bvalid@-1
    commit

  cover cp_cpu_b_valid_ready:
    flow peripheral.axi4lite_axi_bvalid@0 cpu.axi4lite_axi_bvalid@-1
    commit

  branch axi_w_b
```

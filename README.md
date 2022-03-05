# Sequence of Covers with Yosys (SCY)

SCY is a tool for creating deep formal traces, by splitting the property to
cover into smaller cover properties, which the solver will cover eagerly
in sequence.

The cover points themselves are SVA cover properties. Additional data-flow
analysis properties and SVA restrict/assume properties can be used to further
narrow the search space to certain traces.

## Example SCY Project

The `scy` command-line tool reads a `.scy` file that describes the design to check,
and the individual steps to cover. For example [`example/axixfer.scy`](example/axixfer.scy):

```
[design]
read -sv top.sv cpu.sv mem.sv bus.sv fifo.sv
prep -top top

[sequence]
depth 20
engine btor btormc

cover cp_reset_done:
  commit reset

cover cp_cpu_ar_valid_ready:
  cover cp_mem_ar_valid_ready:
    flow cpu1.ARVALID@0 mem.ARVALID@-1
    flow cpu1.ARADDR@0 mem.ARADDR@-1
    commit

  cover cp_mem_r_valid_ready:
    flow mem.ARVALID@0 mem.RVALID@-1
    flow mem.ARADDR@0 mem.RDATA@-1
    commit

  cover cp_cpu_r_valid_ready:
    flow mem.RVALID@0 cpu1.RVALID@-1
    flow mem.RDATA@0 cpu1.RDATA@-1
    commit

  branch axi_ar_r

cover cp_cpu_aw_valid_ready:
  cover cp_mem_aw_valid_ready:
    flow cpu1.AWVALID@0 mem.AWVALID@-1
    flow cpu1.AWADDR@0 mem.AWADDR@-1
    commit

  cover cp_mem_b_valid_ready:
    flow mem.AWVALID@0 mem.BVALID@-1
    commit

  cover cp_cpu_b_valid_ready:
    flow mem.BVALID@0 cpu1.BVALID@-1
    commit

  branch axi_aw_b

cover cp_cpu_w_valid_ready:
  cover cp_mem_w_valid_ready:
    flow cpu1.WVALID@0 mem.WVALID@-1
    flow cpu1.WDATA@0 mem.WDATA@-1
    commit

  cover cp_mem_b_valid_ready:
    flow mem.WVALID@0 mem.BVALID@-1
    commit

  cover cp_cpu_b_valid_ready:
    flow mem.BVALID@0 cpu1.BVALID@-1
    commit

  branch axi_w_b
```

Running `scy`:

```
$ scy -j4 axixfers.scy
Generating axixfers/Makefile
Generating axixfers/L09_00_cp_reset_done.sby
Generating axixfers/L10_09_reset.sh
Generating axixfers/L12_09_cp_cpu_ar_valid_ready.sby
Generating axixfers/L13_12_cp_mem_ar_valid_ready.sby
Generating axixfers/L18_13_cp_mem_r_valid_ready.sby
Generating axixfers/L23_18_cp_cpu_r_valid_ready.sby
Generating axixfers/L28_23_axi_ar_r.sh
Generating axixfers/L30_09_cp_cpu_aw_valid_ready.sby
Generating axixfers/L31_30_cp_mem_aw_valid_ready.sby
Generating axixfers/L36_31_cp_mem_b_valid_ready.sby
Generating axixfers/L40_36_cp_cpu_r_valid_ready.sby
Generating axixfers/L44_40_axi_aw_b.sh
Generating axixfers/L46_09_cp_cpu_w_valid_ready.sby
Generating axixfers/L47_46_cp_mem_w_valid_ready.sby
Generating axixfers/L52_47_cp_mem_b_valid_ready.sby
Generating axixfers/L56_52_cp_cpu_r_valid_ready.sby
Generating axixfers/L60_56_axi_w_b.sh
Running "make -j4 -C axixfers".
... ... ...
Chunks:
  L09       0 .. 11  =>  12  cp_reset_done
  |L12     11 .. 13  =>   2  cp_cpu_ar_valid_ready
  | L13    13 .. 16  =>   3  cp_mem_ar_valid_ready
  |  L18   16 .. 18  =>   2  cp_mem_r_valid_ready
  |   L23  18 .. 21  =>   3  cp_cpu_r_valid_ready
  `L30     11 .. 13  =>   2  cp_cpu_aw_valid_ready
  | L31    13 .. 16  =>   3  cp_mem_aw_valid_ready
  |  L36   16 .. 19  =>   3  cp_mem_b_valid_ready
  |   L40  19 .. 22  =>   3  cp_cpu_b_valid_ready
  `L46     11 .. 14  =>   3  cp_cpu_w_valid_ready
    L47    14 .. 17  =>   3  cp_mem_w_valid_ready
     L52   17 .. 19  =>   2  cp_mem_b_valid_ready
      L56  19 .. 22  =>   3  cp_cpu_b_valid_ready

Traces:
  reset     12 cycles [L09]
  axi_ar_r  22 cycles [L09 L12 L13 L18 L23]
  axi_aw_b  23 cycles [L09 L30 L31 L36 L40]
  axi_w_b   23 cycles [L09 L46 L47 L52 L56]
```

connect
targets -set -filter {name =~ "APU"}
rst -system
after 2000
targets -set -filter {name =~ "APU"}
source "hw/vivado/build/ldacs_zed/ldacs_zed.gen/sources_1/bd/system/ip/system_ps7_0/ps7_init.tcl"
ps7_init
ps7_post_config
targets -set -filter {name =~ "*xc7z010*"}
fpga -file "hw/vivado/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit"
targets -set -filter {name =~ "*Cortex-A9*#0*"}
configparams force-mem-access 1
puts "DDR=[mrd -force 0x00100000 1]"
dow "sw/uart_bridge.elf"
con
puts "BOARD_BRIDGE_RUNNING"
exit
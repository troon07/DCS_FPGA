connect
targets -set -filter {name =~ "*Cortex-A9*#0*"}
rst -processor
source "hw/vivado/build/ldacs_zed/ldacs_zed.gen/sources_1/bd/system/ip/system_ps7_0/ps7_init.tcl"
ps7_init
ps7_post_config
configparams force-mem-access 1
puts "OCM=[mrd -force 0xFFFC0000 1]"
puts "DDR=[mrd -force 0x00100000 1]"
exit
connect
targets -set -filter {name =~ "*Cortex-A9*#0*"}
rst -processor
after 100
source [file join [file dirname [info script]] hw/vivado/build/ldacs_zed/ldacs_zed.gen/sources_1/bd/system/ip/system_ps7_0/ps7_init.tcl]
ps7_init
ps7_post_config
configparams force-mem-access 1
puts "OCM"
if {[catch {mwr 0xFFFC0000 0x12345678; puts [mrd 0xFFFC0000]} err]} { puts "OCM_FAIL: $err" }
puts "DDR"
if {[catch {mwr 0x00100000 0xA5A5A5A5; puts [mrd 0x00100000]} err]} { puts "DDR_FAIL: $err" }
exit

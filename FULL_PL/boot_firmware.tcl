# Programs this variant only; board preset initializes DDR, MIO and clocks.
set root [file normalize [file dirname [info script]]]
set bit [file join $root hw/vivado/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit]
set psinit [file join $root hw/vivado/build/ldacs_zed/ldacs_zed.gen/sources_1/bd/system/ip/system_ps7_0/ps7_init.tcl]
if {![file exists $psinit]} {
    set psinit [file join $root hw/vivado/build/ldacs_zed/ldacs_zed.srcs/sources_1/bd/system/ip/system_ps7_0/ps7_init.tcl]
}
set elf [file join $root sw/uart_bridge.elf]
foreach required [list $bit $psinit $elf] {if {![file exists $required]} {error "Missing build artifact: $required"}}
connect
if {[llength [targets -filter {name =~ "*xc7z010*"}]] == 0} {error "EDGE Z7-10 xc7z010 not found"}
targets -set -filter {name =~ "*Cortex-A9*#0*"}
rst -processor
source $psinit
ps7_init
ps7_post_config
targets -set -filter {name =~ "*xc7z010*"}
fpga -file $bit
targets -set -filter {name =~ "*Cortex-A9*#0*"}
configparams force-mem-access 1
dow $elf
con
puts "BOOT_OK: research firmware running"
exit

# Programs this variant only; board preset initializes DDR, MIO and clocks.
set root [file normalize [file dirname [info script]]]
set family [file normalize $root/hw/vivado/build/dfx]
if {$argc>0} {set family [file normalize [lindex $argv 0]]}
set routed [file join $family routed_manifest.json]
set images [file join $family images.json]
foreach required [list $routed $images] {if {![file exists $required]} {error "Build and package verified DFX images first: $required"}}
set f [open $routed r];set contents [read $f];close $f
if {![regexp {"pr_verify_passed"\s*:\s*true} $contents]} {error "DFX implementation is incomplete or failed"}
set build_root [file dirname $family]
set bit [file join $family hybrid.bit]
set psinit [file join $build_root ldacs_zed/ldacs_zed.gen/sources_1/bd/system/ip/system_ps7_0/ps7_init.tcl]
if {![file exists $psinit]} {
    set psinit [file join $build_root ldacs_zed/ldacs_zed.srcs/sources_1/bd/system/ip/system_ps7_0/ps7_init.tcl]
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

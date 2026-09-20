open_hw_manager
connect_hw_server -allow_non_jtag
set target [get_hw_targets -filter {TARGET_NAME =~ "*210319A288EEA*"}]
if {[llength $target] == 0} {
    set target [lindex [get_hw_targets] 0]
}
puts "Connecting to target: $target"
open_hw_target $target
set_property PARAM.FREQUENCY 10000000 [get_hw_targets $target]
refresh_hw_target
set devs [get_hw_devices]
puts "Devices found: $devs"
if {[llength $devs] > 0} {
    set dev [lindex $devs 1]
    if {[llength $dev] == 0} { set dev [lindex $devs 0] }
    current_hw_device $dev
    refresh_hw_device $dev
    set bit_file [file normalize "hw/vivado/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit"]
    puts "Programming $dev with $bit_file"
    set_property PROGRAM.FILE $bit_file $dev
    program_hw_devices $dev
    puts ">>> SUCCESS: FPGA PROGRAMMED <<<"
}
close_hw_target
disconnect_hw_server
close_hw_manager
exit

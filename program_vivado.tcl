open_hw_manager
connect_hw_server -allow_non_jtag
set target [lindex [get_hw_targets] 0]
open_hw_target $target
puts "TARGET OPENED: $target"
set dev [get_hw_devices xc7z010_1]
if {[llength $dev] == 0} {
    set dev [lindex [get_hw_devices] 1]
}
puts "TARGET DEVICE: $dev"
set bit_file [file normalize "hw/vivado/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit"]
puts "BITSTREAM: $bit_file"
set_property PROGRAM.FILE $bit_file $dev
program_hw_devices $dev
puts ">>> FPGA PROGRAMMED SUCCESSFULLY VIA VIVADO HW MANAGER <<<"
close_hw_target
disconnect_hw_server
close_hw_manager
exit

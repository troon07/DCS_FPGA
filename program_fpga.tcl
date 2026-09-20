open_hw_manager
connect_hw_server -allow_non_jtag
set target [lindex [get_hw_targets] 0]
open_hw_target $target
puts "TARGET OPENED: [get_hw_targets -filter {IS_OPENED == 1}]"
set dev [get_hw_devices xc7z010_1]
puts "TARGET FPGA DEVICE: $dev"
set bit_file [file normalize "hw/vivado/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit"]
puts "PROGRAMMING BITSTREAM: $bit_file"
set_property PROGRAM.FILE $bit_file $dev
program_hw_devices $dev
puts "========================================================"
puts ">>> SUCCESS: ZYNQ FPGA PROGRAMMED WITH BITSTREAM! <<<"
puts "========================================================"
close_hw_target
disconnect_hw_server
close_hw_manager
exit

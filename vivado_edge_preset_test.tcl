set out_dir [file normalize "vivado_board_preset_test"]
create_project board_preset_test $out_dir -part xc7z020clg400-1 -force
set_property board_part allaboutfpga.com:edgez7_20:part0:1.0 [current_project]
create_bd_design system
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 ps7]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config {apply_board_preset "1"} $ps
puts "PRESET=[get_property CONFIG.PCW_IMPORT_BOARD_PRESET $ps]"
puts "UART0=[get_property CONFIG.PCW_UART0_PERIPHERAL_ENABLE $ps]"
puts "UART0_IO=[get_property CONFIG.PCW_UART0_UART0_IO $ps]"
puts "DDR_PART=[get_property CONFIG.PCW_UIPARAM_DDR_PARTNO $ps]"
puts "FCLK0=[get_property CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ $ps]"
validate_bd_design
exit
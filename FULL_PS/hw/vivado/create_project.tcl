# FULL_PS: PS7 + DDR + fixed IO only. NO decoder, AXI DMA or PL algorithms.
set origin [file normalize [file dirname [info script]]]
set board_repo [file normalize $origin/../../board_details]
set_param board.repoPaths [list $board_repo]
create_project ldacs_zed $origin/build/ldacs_zed -part xc7z010clg400-1 -force
set_property board_part allaboutfpga.com:edgez7_10:part0:1.0 [current_project]
create_bd_design system
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 ps7]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 -config {apply_board_preset "1"} $ps
set_property CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {70} $ps
make_bd_intf_pins_external [get_bd_intf_pins ps7/DDR]
make_bd_intf_pins_external [get_bd_intf_pins ps7/FIXED_IO]
validate_bd_design
save_bd_design
generate_target all [get_files system.bd]
make_wrapper -files [get_files system.bd] -top
set wrappers [concat [glob -nocomplain $origin/build/ldacs_zed/ldacs_zed.gen/sources_1/bd/system/hdl/system_wrapper.v] [glob -nocomplain $origin/build/ldacs_zed/ldacs_zed.srcs/sources_1/bd/system/hdl/system_wrapper.v]]
if {[llength $wrappers]==0} {error "Generated system wrapper missing"}
add_files -norecurse $wrappers
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
puts "FULL_PS_PROJECT_CREATED"

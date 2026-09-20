create_project board_query [file normalize "vivado_board_query_project"] -part xc7z020clg400-1 -force
set_property board_part allaboutfpga.com:edgez7_20:part0:1.0 [current_project]
puts "INTERFACES:[get_board_part_interfaces]"
exit
open_project build/ldacs_zed/ldacs_zed.xpr
open_bd_design build/ldacs_zed/ldacs_zed.srcs/sources_1/bd/system/system.bd
validate_bd_design
save_bd_design
make_wrapper -files [get_files system.bd] -top
add_files -norecurse [glob build/ldacs_zed/ldacs_zed.gen/sources_1/bd/system/hdl/system_wrapper.v]
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1
save_project
puts "PROJECT_GENERATION_OK"
exit
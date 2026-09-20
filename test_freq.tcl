open_hw_manager
connect_hw_server -allow_non_jtag
set target [lindex [get_hw_targets] 0]
puts "Configuring target $target frequency to 3MHz..."
set_property PARAM.FREQUENCY 3000000 [get_hw_targets $target]
catch {open_hw_target $target} err
puts "open_hw_target result: $err"
set devs [get_hw_devices]
puts "Devices detected: $devs"
if {[llength $devs] > 0} {
    foreach d $devs {
        puts "Found device: $d | [get_property PART $d]"
    }
}
close_hw_manager
exit

open_hw_manager
connect_hw_server -allow_non_jtag
puts "SERVER CONNECTED"
set targets [get_hw_targets]
puts "HW TARGETS: $targets"
if {[llength $targets] > 0} {
    open_hw_target [lindex $targets 0]
    puts "OPEN TARGET: [get_hw_targets -filter {IS_OPENED == 1}]"
    set devs [get_hw_devices]
    puts "HW DEVICES: $devs"
    foreach dev $devs {
        puts "DEVICE: $dev | PART: [get_property PART $dev]"
    }
    close_hw_target
}
disconnect_hw_server
close_hw_manager
exit

open_hw_manager
connect_hw_server -allow_non_jtag
set targets [get_hw_targets]
puts "TARGETS: $targets"
if {[llength $targets] == 0} {
    puts "NO_TARGETS_FOUND"
} else {
    set target [lindex $targets 0]
    if {[catch {open_hw_target $target} err]} {
        puts "TARGET_OPEN_FAILED: $err"
    } else {
        set devs [get_hw_devices]
        puts "DEVICES: $devs"
        close_hw_target $target
    }
}
disconnect_hw_server
close_hw_manager
exit

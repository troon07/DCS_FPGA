open_hw_manager
connect_hw_server -allow_non_jtag
refresh_hw_server
set targets [get_hw_targets]
puts "Targets detected: $targets"
foreach t $targets {
    puts "--> Opening target: $t"
    open_hw_target $t
    set devs [get_hw_devices]
    puts "--> Devices on target $t: $devs"
    foreach d $devs {
        puts "    Device: $d  (Part: [get_property PART $d])"
        if {[string match "*xc7z010*" [get_property PART $d]]} {
            set bit_file [file normalize "hw/vivado/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit"]
            puts "    >>> Found xc7z010! Programming bitstream $bit_file..."
            set_property PROGRAM.FILE $bit_file $d
            program_hw_devices $d
            puts "    >>> SUCCESS: xc7z010 FPGA PROGRAMMED SUCCESSFULLY! <<<"
        }
    }
    close_hw_target $t
}
disconnect_hw_server
close_hw_manager
exit

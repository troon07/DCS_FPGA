# detect_board_full.tcl
# Full hardware check: detect JTAG targets, read device ID, check board
# Usage: xsdb.bat detect_board_full.tcl

puts "=== LDACS Hardware Detection ==="
puts "Connecting to hw_server (local)..."

if {[catch {connect} err]} {
    puts "ERR_CONNECT: Cannot connect to hw_server: $err"
    exit 1
}
puts "OK: hw_server connected"

# List all JTAG targets
puts "\n=== JTAG Targets ==="
set targets [targets]
puts $targets

set tlist [get_hw_targets]
if {[llength $tlist] == 0} {
    puts "\nERR_NO_TARGET: No JTAG hardware targets found."
    puts "  -> Is the ZedBoard USB-JTAG cable connected?"
    puts "  -> Is the board powered on?"
    exit 1
}

puts "\nFound [llength $tlist] JTAG target(s):"
foreach t $tlist { puts "  Target: $t" }

# Open first target and enumerate devices
set t0 [lindex $tlist 0]
puts "\n=== Opening target: $t0 ==="
open_hw_target $t0

set devs [get_hw_devices]
puts "Devices on target:"
foreach d $devs {
    set idcode [get_property IDCODE $d]
    set name   [get_property NAME   $d]
    puts "  Device: $name  IDCODE: $idcode"
}

puts "\n=== Board detected successfully ==="
puts "DETECT_OK"
close_hw_target
exit 0

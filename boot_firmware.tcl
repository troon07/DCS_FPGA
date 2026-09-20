# boot_firmware.tcl
# XSDB script: programs bitstream then loads & runs uart_bridge.elf on Zynq ARM
# Usage: xsdb.bat boot_firmware.tcl
# This replaces the old OCM/JTAG memory-injection approach entirely.
# After this runs, the ARM is executing uart_bridge firmware, listening on UART0.

set BIT_FILE  [file join [file dirname [info script]] hw/vivado/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit]
set ELF_FILE  [file join [file dirname [info script]] sw/uart_bridge.elf]
set PS7_INIT  [file join [file dirname [info script]] hw/vivado/build/ldacs_zed/ldacs_zed.gen/sources_1/bd/system/ip/system_ps7_0/ps7_init.tcl]

if {![file exists $ELF_FILE]} {
    puts "ERR_NO_ELF: $ELF_FILE not found. Run: python build_firmware.py"
    exit 1
}
if {![file exists $BIT_FILE]} {
    puts "ERR_NO_BIT: $BIT_FILE not found."
    exit 1
}
if {![file exists $PS7_INIT]} {
    puts "ERR_NO_PS7_INIT: $PS7_INIT not found. Recreate the EDGE Z7-10 Vivado project first."
    exit 1
}

# --- Connect to hw_server and detect target (XSDB commands, not Vivado Tcl) ---
connect
set fpga_targets [targets -filter {name =~ "*xc7z010*"}]
if {[llength $fpga_targets] == 0} {
    puts "ERR_NO_TARGET: No xc7z010 JTAG target found. Is the EDGE Z7-10 powered on?"
    exit 1
}

# --- Switch to ARM Cortex-A9 target for firmware load ---
targets -set -filter {name =~ "*Cortex-A9*#0*"}

# Initialize the PS exclusively with Tcl generated from the current EDGE
# Z7-10 preset.  Do not use hand-coded DDR, MIO, clock, or SLCR settings.
rst -processor
after 100
source $PS7_INIT
ps7_init
ps7_post_config

# Program FPGA fabric after PS initialization.
targets -set -filter {name =~ "*xc7z010*"}
fpga -file $BIT_FILE
puts "INFO: Bitstream programmed OK"

# Return to the suspended ARM core for the firmware download.
targets -set -filter {name =~ "*Cortex-A9*#0*"}
configparams force-mem-access 1

# Load uart_bridge.elf into the initialized DDR image region (0x01000000).
puts "INFO: Loading $ELF_FILE ..."
dow $ELF_FILE

# Launch ARM execution
puts "INFO: Starting ARM core — firmware running on UART0"
con

# Give firmware 500ms to init UART and verify decoder VERSION register
after 500

puts "BOOT_OK: uart_bridge firmware is running. Use the board USB-UART COM port."
exit

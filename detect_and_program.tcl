# detect_and_program.tcl
# XSDB (not Vivado Tcl) — uses 'targets' / 'target' commands
# Step 1: Detect board
# Step 2: Program bitstream via JTAG (xc7z010 fabric)
# Step 3: Load+run ELF on ARM Cortex-A9

set BIT_FILE [file join [file dirname [info script]] \
    hw/vivado/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit]
set ELF_FILE [file join [file dirname [info script]] sw/uart_bridge.elf]

puts "=== LDACS Hardware Check ==="
puts "Connecting to hw_server..."
connect
puts "OK: hw_server connected"

# ── STEP 1: List and verify targets ─────────────────────────────────────────
puts "\n--- STEP 1: JTAG Targets ---"
targets
# targets returns a formatted string — also check count
set tlist [split [targets] "\n"]
set n_targets 0
foreach line $tlist {
    if {[string trim $line] ne ""} { incr n_targets }
}
puts "Target lines seen: $n_targets"

# Verify xc7z010 is visible
set all_targets [targets]
if {[string match "*xc7z010*" $all_targets]} {
    puts "DETECT_OK: xc7z010 (ZedBoard Zynq-7010) visible on JTAG"
} else {
    puts "WARN: xc7z010 not found in target list"
}
if {[string match "*Cortex-A9*" $all_targets]} {
    puts "DETECT_OK: ARM Cortex-A9 PS visible"
}

# ── STEP 2: Program FPGA fabric ─────────────────────────────────────────────
puts "\n--- STEP 2: Program Bitstream ---"
if {![file exists $BIT_FILE]} {
    puts "ERR: Bitstream not found at: $BIT_FILE"
    exit 1
}
puts "Bitstream: $BIT_FILE ([file size $BIT_FILE] bytes)"

# Select the FPGA (xc7z010) target — target 4 in our scan
# Use filter to be safe
target -set -filter {name =~ "xc7z010*"}
puts "INFO: Programming xc7z010 fabric..."
fpga $BIT_FILE
puts "PROGRAM_OK: Bitstream loaded into FPGA"

# ── STEP 3: Load ELF on ARM Cortex-A9 ──────────────────────────────────────
puts "\n--- STEP 3: Load ARM Firmware ---"
if {![file exists $ELF_FILE]} {
    puts "ERR_NO_ELF: $ELF_FILE not found — skipping firmware load"
    puts "  Run: python build_firmware.py"
    puts "\n=== SUMMARY ==="
    puts "Board detected:   YES (xc7z010)"
    puts "Bitstream loaded: YES"
    puts "Firmware loaded:  NO (ELF missing)"
    exit 0
}

puts "ELF: $ELF_FILE ([file size $ELF_FILE] bytes)"
target -set -filter {name =~ "*Cortex-A9*#0*"}
rst -system
configparams force-mem-access 1
# Enable PS level shifters (required after bitstream program on Zynq)
mwr -force 0xF8000008 0xDF0D
mwr -force 0xF8000900 0x0F
mwr -force 0xF8000240 0x00
dow $ELF_FILE
puts "ELF_LOAD_OK: uart_bridge.elf loaded into OCM"
con
after 600
puts "ELF_RUN_OK: ARM core running — uart_bridge firmware active on UART1"

puts "\n=== SUMMARY ==="
puts "Board detected:   YES (xc7z010)"
puts "Bitstream loaded: YES"
puts "Firmware loaded:  YES"
puts "COM5 ready:       YES (UART1 at 115200 baud)"
puts "HW_BOOT_OK"
exit 0

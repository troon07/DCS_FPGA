
connect
set targets_list [targets]
if {[llength [targets -filter {name =~ "*Cortex-A9*#0*"}]] == 0} {
    puts "ERR_NO_TARGET"
    exit
}
targets -set -filter {name =~ "*Cortex-A9*#0*"}
configparams force-mem-access 1

# Unlock SLCR & enable Level Shifters & GP0
if {[catch {
    mwr -force 0xf8000008 0xdf0d
    mwr -force 0xf8000900 0xf
    mwr -force 0xf8000240 0x0
} err]} {
    puts "ERR_UNPOWERED: $err"
    exit
}

# Reset decoder & counters
mwr -force 0x40000000 0x3
after 5
mwr -force 0x40000000 0x0

# Configure Decoder Registers
mwr -force 0x40000008 0
mwr -force 0x4000000C 4884
mwr -force 0x40000010 6
mwr -force 0x40000014 101

# Load encoded vector into OCM
dow -data "tv_vit_in.bin" 0x00000000

# Reset DMA
mwr -force 0x40400000 4
mwr -force 0x40400030 4
after 5

# Clear DMA Status
mwr -force 0x40400004 0xFFFFFFFF
mwr -force 0x40400034 0xFFFFFFFF

# Arm S2MM (receive from decoder to OCM 0x00003000)
mwr -force 0x40400048 0x00003000
mwr -force 0x40400030 1
mwr -force 0x40400058 546

# Trigger MM2S (send from OCM 0x00000000 to decoder)
mwr -force 0x40400018 0x00000000
mwr -force 0x40400000 1
mwr -force 0x40400028 9768

after 80

# Read back decoded bytes from OCM 0x00003000
mrd -bin -file tv_hw_out.bin 0x00003000 137
puts [format "DEC_RS_CORR: %d" [mrd -value 0x4000001C]]
puts [format "DEC_RS_FAIL: %d" [mrd -value 0x40000020]]
exit

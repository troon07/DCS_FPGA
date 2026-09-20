
connect
targets -set -filter {name =~ "*Cortex-A9*#0*"}
configparams force-mem-access 1

# Unlock SLCR & enable Level Shifters & GP0
mwr -force 0xf8000008 0xdf0d
mwr -force 0xf8000900 0xf
mwr -force 0xf8000240 0x0

# Load encoded vector into OCM
dow -data "tv/vit_in.bin" 0x00000000

# Configure Decoder Registers
mwr -force 0x40000000 0
mwr -force 0x40000004 4884
mwr -force 0x40000008 6
mwr -force 0x4000000c 101

# Trigger DMA S2MM (receive from decoder to OCM 0x00003000)
mwr -force 0x40400030 4
after 5
mwr -force 0x40400048 0x00003000
mwr -force 0x40400030 1
mwr -force 0x40400058 546

# Trigger DMA MM2S (send from OCM 0x00000000 to decoder)
mwr -force 0x40400000 4
after 5
mwr -force 0x40400018 0x00000000
mwr -force 0x40400000 1
mwr -force 0x40400028 9768

after 50

# Read back decoded bytes from OCM 0x00003000
mrd -bin -file hw_out.bin 0x00003000 546
exit

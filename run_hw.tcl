
connect
puts "--> Programming FPGA bitstream system_wrapper.bit..."
targets -set -filter {name =~ "*xc7z010*"}
fpga "hw/vivado/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit"
after 200

# Select ARM Cortex-A9 target directly and enable force memory access
set a9 [lindex [targets -filter {name =~ "*Cortex-A9*#0*"}] 0]
targets $a9
configparams force-mem-access 1

# Unlock SLCR, enable Level Shifters, & enable GP0 AXI Master
mwr -force 0xf8000008 0xdf0d
mwr -force 0xf8000900 0xf
mwr -force 0xf8000240 0x0

puts "--> Loading encoded test vector vit_in.bin into OCM (0x00000000)..."
dow -data "tv/vit_in.bin" 0x00000000

puts "--> Configuring Decoder IP Registers..."
mwr -force 0x40000000 0
mwr -force 0x40000004 4884
mwr -force 0x40000008 6
mwr -force 0x4000000c 101

puts "--> Triggering AXI DMA Transfers..."
mwr -force 0x40400000 4
mwr -force 0x40400030 4
after 10

mwr -force 0x40400048 0x00003000
mwr -force 0x40400030 1
mwr -force 0x40400058 546

mwr -force 0x40400018 0x00000000
mwr -force 0x40400000 1
mwr -force 0x40400028 4884

after 100
puts "--> Reading back decoded payload from OCM (0x00003000) to hw_out.bin..."
mrd -bin -file hw_out.bin 0x00003000 546
puts "--> Done!"
exit

connect
targets -set -filter {name =~ "*Cortex-A9*#0*"}

mwr 0xf8000008 0xdf0d
mwr 0xf8000900 0xf
mwr 0xf8000240 0x0
memmap -addr 0x40000000 -size 0x1000000 -flags 3
memmap -addr 0x40400000 -size 0x100000 -flags 3

puts "MM2S_DMACR: [mrd -force 0x40400000]"
puts "S2MM_DMACR: [mrd -force 0x40400030]"
puts "S2MM_DMASR: [mrd -force 0x40400034]"

# Set up decoder config
mwr -force 0x40000000 0x0
mwr -force 0x40000004 4884
mwr -force 0x40000008 6
mwr -force 0x4000000c 101

# Reset DMAs
mwr -force 0x40400000 4
mwr -force 0x40400030 4
after 10

# Start S2MM (Rx) first
mwr -force 0x40400048 0x00003000
mwr -force 0x40400030 1
mwr -force 0x40400058 546

# Start MM2S (Tx) second
mwr -force 0x40400018 0x00000000
mwr -force 0x40400000 1
mwr -force 0x40400028 4884

after 50
puts "S2MM_DMASR AFTER: [mrd -force 0x40400034]"
puts "MM2S_DMASR AFTER: [mrd -force 0x40400004]"
exit

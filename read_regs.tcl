connect
targets -set -filter {name =~ "*Cortex-A9*#0*"}
configparams force-mem-access 1
mwr -force 0xf8000008 0xdf0d
mwr -force 0xf8000900 0xf
mwr -force 0xf8000240 0x0

puts "Testing base addresses for LDACS Decoder VERSION (Expected: 0x4C444331 / LDC1):"
catch { puts [format "  [0x40000000] VERSION at 0x40000024 = 0x%08X" [mrd -value 0x40000024]] } err1
if {$err1 ne ""} { puts "  0x40000024 error: $err1" }

catch { puts [format "  [0x43C00000] VERSION at 0x43C00024 = 0x%08X" [mrd -value 0x43C00024]] } err2
if {$err2 ne ""} { puts "  0x43C00024 error: $err2" }

puts "Testing DMA registers (DMACR at offset 0x00, DMASR at offset 0x04):"
catch { puts [format "  [0x40400000] DMA MM2S_DMACR = 0x%08X" [mrd -value 0x40400000]] } err3
if {$err3 ne ""} { puts "  0x40400000 error: $err3" }

catch { puts [format "  [0x41E00000] DMA MM2S_DMACR = 0x%08X" [mrd -value 0x41E00000]] } err4
if {$err4 ne ""} { puts "  0x41E00000 error: $err4" }

exit

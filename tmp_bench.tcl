
connect
targets -set -filter {name =~ "*Cortex-A9*#0*"}

# Enable AXI Bus access in OCM/SLCR
mwr 0xf8000008 0xdf0d
mwr 0xf8000900 0xf
mwr 0xf8000240 0x0
memmap -addr 0x40000000 -size 0x1000000 -flags 3

# Test multi-frame decoder benchmark (5 iterations)
set num_runs 5
set start_time [clock milliseconds]

for {set i 0} {$i < $num_runs} {incr i} {
    # Configure decoder parameters
    mwr 0x40000000 0x0
    mwr 0x40000004 4884
    mwr 0x40000008 6
    mwr 0x4000000c 101

    # Reset MM2S & S2MM DMA
    mwr 0x40400000 4
    mwr 0x40400030 4
    after 1

    # Set S2MM destination (0x00003000) & enable length (546 bytes)
    mwr 0x40400048 0x00003000
    mwr 0x40400030 1
    mwr 0x40400058 546

    # Set MM2S source (0x00000000) & enable length (4884 bytes)
    mwr 0x40400018 0x00000000
    mwr 0x40400000 1
    mwr 0x40400028 4884

    # Wait for DMA completion
    set status [mrd -force 0x40400034]
    while {[expr {[lindex $status 1] & 0x1000}] == 0} {
        after 1
        set status [mrd -force 0x40400034]
    }
}

set end_time [clock milliseconds]
set elapsed [expr $end_time - $start_time]
puts "BENCHMARK_RESULT: total_ms=$elapsed runs=$num_runs"
exit

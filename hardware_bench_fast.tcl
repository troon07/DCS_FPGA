connect
targets -set -filter {name =~ "*Cortex-A9*#0*"}

mwr 0xf8000008 0xdf0d
mwr 0xf8000900 0xf
mwr 0xf8000240 0x0
memmap -addr 0x40000000 -size 0x1000000 -flags 3
memmap -addr 0x40400000 -size 0x100000 -flags 3

set num_runs 100
set start_t [clock milliseconds]

for {set i 0} {$i < $num_runs} {incr i} {
    mwr -force 0x40000000 0x0
    mwr -force 0x40000004 4884
    mwr -force 0x40000008 6
    mwr -force 0x4000000c 101

    mwr -force 0x40400048 0x00003000
    mwr -force 0x40400030 1
    mwr -force 0x40400058 546

    mwr -force 0x40400018 0x00000000
    mwr -force 0x40400000 1
    mwr -force 0x40400028 4884
}

set end_t [clock milliseconds]
set total_ms [expr $end_t - $start_t]
set per_frame_ms [expr $total_ms / double($num_runs)]
set total_bytes [expr $num_runs * 546]
set throughput_kbps [expr ($total_bytes * 8.0) / $total_ms]

puts "=========================================================="
puts "  LDACS ZYNQ-7000 HARDWARE BENCHMARK RESULTS (JTAG / OCM)"
puts "=========================================================="
puts "  Total frames processed : $num_runs"
puts "  Total execution time   : ${total_ms} ms"
puts "  Latency per frame      : ${per_frame_ms} ms"
puts "  Decoded payload output : [expr $total_bytes / 1024.0] KB"
puts "  Measured throughput    : ${throughput_kbps} kbps"
puts "=========================================================="
exit

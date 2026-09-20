connect
targets -set -filter {name =~ "*Cortex-A9*#0*"}

mwr 0xf8000008 0xdf0d
mwr 0xf8000900 0xf
mwr 0xf8000240 0x0
memmap -addr 0x40000000 -size 0x1000000 -flags 3
memmap -addr 0x40400000 -size 0x100000 -flags 3

set num_runs 5
set start_time [clock milliseconds]

for {set i 0} {$i < $num_runs} {incr i} {
    mwr -force 0x40000000 0x0
    mwr -force 0x40000004 4884
    mwr -force 0x40000008 6
    mwr -force 0x4000000c 101

    mwr -force 0x40400000 4
    mwr -force 0x40400030 4
    after 1

    mwr -force 0x40400048 0x00003000
    mwr -force 0x40400030 1
    mwr -force 0x40400058 546

    mwr -force 0x40400018 0x00000000
    mwr -force 0x40400000 1
    mwr -force 0x40400028 4884

    set status [mrd -force 0x40400034]
    while {[expr {[lindex $status 1] & 0x1000}] == 0} {
        after 1
        set status [mrd -force 0x40400034]
    }
}

set end_time [clock milliseconds]
set elapsed [expr $end_time - $start_time]
puts "BENCHMARK_RESULT: total_ms=$elapsed runs=$num_runs avg_ms_per_frame=[expr $elapsed / 5.0]"
exit

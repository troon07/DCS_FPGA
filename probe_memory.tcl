connect
targets -set -filter {name =~ "*Cortex-A9*#0*"}
configparams force-mem-access 1
foreach addr {0x00000000 0x00100000 0x01000000 0x10000000} {
  if {[catch {mrd -force $addr 1} out]} { puts "READ_FAIL $addr: $out" } else { puts "READ_OK $addr: $out" }
}
exit
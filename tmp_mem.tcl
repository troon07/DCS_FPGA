connect
targets -set -filter {name =~ "*Cortex-A9*#0*"}
configparams force-mem-access 1
puts "TARGET=[targets]"
puts "OCM=[mrd -force 0xFFFC0000 1]"
puts "DDR=[mrd -force 0x00100000 1]"
exit
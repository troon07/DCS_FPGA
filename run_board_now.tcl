connect
puts [targets]
targets -set -filter {name =~ "*xc7z010*"}
fpga -file "hw/vivado/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit"
puts "BITSTREAM_PROGRAMMED"
targets -set -filter {name =~ "*Cortex-A9*#0*"}
configparams force-mem-access 1
puts "CPU_SELECTED"
dow "sw/uart_bridge.elf"
puts "FIRMWARE_LOADED"
con
puts "FIRMWARE_STARTED"
exit
connect
targets -set -filter {name =~ "*xc7z010*"}
fpga "hw/vivado/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit"
puts "FPGA Bitstream Programmed Successfully!"
exit

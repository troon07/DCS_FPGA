import os, subprocess, time

print("==========================================================================")
print("  STEP 1: Generate Python Reference Model Test Vectors")
print("==========================================================================")
subprocess.run(["python3", "model/ldacs_ref.py", "--out", "tv"], check=True)

print("\n==========================================================================")
print("  STEP 2: Program Bitstream & Execute Live Hardware Decoding via JTAG")
print("==========================================================================")

prog_tcl = """
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
"""
with open("run_hw.tcl", "w") as f:
    f.write(prog_tcl)

res = subprocess.run(["xsdb", "run_hw.tcl"], text=True)

print("\n==========================================================================")
print("  STEP 3: Compare Hardware Decoded Output Against Reference Model")
print("==========================================================================")

with open("hw_out.bin", "rb") as f1, open("tv/hw_expected.bin", "rb") as f2:
    hw_bytes = f1.read()
    exp_bytes = f2.read()

print(f"Hardware Output Byte Count : {len(hw_bytes)} bytes")
print(f"Expected Reference Count   : {len(exp_bytes)} bytes")
print("-" * 74)
print("Hardware Decoded Bytes (First 32 Bytes Hex) :\n", hw_bytes[:32].hex())
print("Golden Reference Bytes (First 32 Bytes Hex) :\n", exp_bytes[:32].hex())
print("-" * 74)

mismatches = sum(1 for a, b in zip(hw_bytes, exp_bytes) if a != b)
if mismatches == 0:
    print("  VERIFICATION RESULT: 100% BIT-EXACT MATCH (0 MISMATCHES)!")
    print("  THE HARDWARE DECODER IS FULLY OPERATIONAL ON ZYNQ FPGA.")
else:
    print(f"  VERIFICATION FAILED: {mismatches} mismatches found!")
print("==========================================================================")

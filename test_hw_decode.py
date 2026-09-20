#!/usr/bin/env python3
import os
import sys
import subprocess

from model.ldacs_ref import (
    frame_layout, randomize, rs_encode, block_interleave,
    conv_encode_punct, helical_interleave, helical_deinterleave,
    bytes_to_bits, TAIL_BITS
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
XSDB_PATH = r"C:\Xilinx\Vitis\2022.2\bin\xsdb.bat"

# Create a test message
msg = "LIVE ZYNQ HARDWARE TEST - ZERO DUMMY VALUES"
raw = msg.encode('utf-8')

lay = frame_layout("qpsk_1_2")
K = lay["rs_k"]
payload_len = lay["payload_bytes"] # 546 bytes
padded = raw + b'\x00' * (payload_len - len(raw))

# Encode through 5 TX stages
rnd = randomize(padded)
cws = [rs_encode(rnd[i * K:(i + 1) * K]) for i in range(lay["num_cw"])]
block_int = block_interleave(cws)
bits = bytes_to_bits(block_int) + [0] * lay["pad_bits"] + [0] * TAIL_BITS
conv = conv_encode_punct(bits, lay["rate"])
tx_helical = helical_interleave(conv)

# RX Stage 1: Helical Deinterleaver
rx_helical_deint = helical_deinterleave(tx_helical)

# Save vit_in.bin (1 byte per bit)
vit_in_bytes = bytes(rx_helical_deint)
with open("tv_vit_in.bin", "wb") as f:
    f.write(vit_in_bytes)

tcl_script = f"""
connect
targets -set -filter {{name =~ "*Cortex-A9*#0*"}}
configparams force-mem-access 1

# Unlock SLCR & enable Level Shifters & GP0
mwr -force 0xf8000008 0xdf0d
mwr -force 0xf8000900 0xf
mwr -force 0xf8000240 0x0

# Reset decoder & counters
mwr -force 0x40000000 0x3
after 5
mwr -force 0x40000000 0x0

# Configure Decoder Registers with EXACT OFFSETS
mwr -force 0x40000008 0
mwr -force 0x4000000C {lay['n_steps']}
mwr -force 0x40000010 {lay['num_cw']}
mwr -force 0x40000014 {lay['rs_n']}

# Load encoded vector into OCM
dow -data "tv_vit_in.bin" 0x00000000

# Reset DMA
mwr -force 0x40400000 4
mwr -force 0x40400030 4
after 10

# Clear DMA Status
mwr -force 0x40400004 0xFFFFFFFF
mwr -force 0x40400034 0xFFFFFFFF

# Arm S2MM (receive from decoder to OCM 0x00003000)
mwr -force 0x40400048 0x00003000
mwr -force 0x40400030 1
mwr -force 0x40400058 {lay['payload_bytes']}

# Trigger MM2S (send from OCM 0x00000000 to decoder)
mwr -force 0x40400018 0x00000000
mwr -force 0x40400000 1
mwr -force 0x40400028 {lay['coded_bits']}

after 100

# Read back decoded bytes
mrd -bin -file tv_hw_out.bin 0x00003000 {lay['payload_bytes']}

puts [format "DEC_STATUS: 0x%08X" [mrd -value 0x40000004]]
puts [format "DEC_FRAMES: %d" [mrd -value 0x40000018]]
puts [format "DEC_RS_CORR: %d" [mrd -value 0x4000001C]]
puts [format "DEC_RS_FAIL: %d" [mrd -value 0x40000020]]
puts [format "DMA MM2S_SR: 0x%08X" [mrd -value 0x40400004]]
puts [format "DMA S2MM_SR: 0x%08X" [mrd -value 0x40400034]]

exit
"""

with open("test_decode.tcl", "w") as f:
    f.write(tcl_script)

print("Executing live hardware decoding on FPGA...")
subprocess.run([XSDB_PATH, "test_decode.tcl"], check=True)

with open("tv_hw_out.bin", "rb") as f:
    hw_out = f.read()

# RX Stage 5: Derandomizer
recovered_padded = randomize(hw_out)
recovered_msg = recovered_padded[:len(raw)].decode('utf-8', errors='replace')

print("\n========================================================")
print("  ORIGINAL TRANSMITTED :", msg)
print("  FPGA RECOVERED TEXT  :", recovered_msg)
print("  BIT EXACT MATCH      :", (padded == recovered_padded))
print("========================================================")

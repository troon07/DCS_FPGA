#!/usr/bin/env bash
# Generates test vectors for the board: tv/<mode>/{tx_bits.bin,payload.bin,...}
# Copy the whole tv/ folder plus sw/ldacs_decode to the ZedBoard SD card.
set -e
cd "$(dirname "$0")/.."
for m in qpsk_1_2 qpsk_2_3 qpsk_3_4 16qam_1_2 16qam_2_3 64qam_1_2 64qam_2_3 64qam_3_4; do
  python3 model/ldacs_ref.py --mode $m --ber 0.005 --seed 42 --out tv/$m | grep -E "channel|RESULT"
done
echo "Vectors in ./tv  (copy to the board)"

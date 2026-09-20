#!/usr/bin/env bash
# Runs the FPGA decoder simulation (Icarus Verilog) for several modes / error patterns,
# comparing the hardware output against the Python reference model.
# Usage: ./scripts/run_sim.sh            (all cases)
#        ./scripts/run_sim.sh quick      (one short case)
set -e
cd "$(dirname "$0")/.."
command -v iverilog >/dev/null || { echo "Install Icarus Verilog: sudo apt install iverilog"; exit 1; }

CASES=(
  "qpsk_1_2  --ber 0.0"
  "qpsk_1_2  --ber 0.02 --seed 7"
  "qpsk_2_3  --ber 0.01 --seed 2"
  "qpsk_3_4  --ber 0.01 --seed 3"
  "qpsk_3_4  --ber 0.03 --seed 4"
  "qpsk_3_4  --ber 0.02 --seed 2"
  "qpsk_3_4  --ber 0.02 --seed 3"
  "16qam_2_3 --bursts 4 --burst-len 40 --seed 5"
  "64qam_3_4 --ber 0.012 --seed 6"
)
[ "$1" = "quick" ] && CASES=("qpsk_1_2 --ber 0.01 --seed 1")

pass=0; fail=0
for c in "${CASES[@]}"; do
  dir="build/sim_$(echo $c | tr ' .-' '___')"
  mkdir -p "$dir"
  python3 model/ldacs_ref.py --mode $c --out "$dir" | grep "channel"
  ( cd "$dir" && iverilog -g2005 -o sim.vvp -I . ../../hw/tb/tb_decoder_top.v ../../hw/rtl/*.v \
      && vvp -n sim.vvp > sim.log )
  if grep -q "TEST PASSED" "$dir/sim.log"; then
    echo "  [PASS] $c"; pass=$((pass+1))
  else
    echo "  [FAIL] $c  (see $dir/sim.log)"; tail -5 "$dir/sim.log"; fail=$((fail+1))
  fi
done
echo "==== $pass passed, $fail failed ===="
[ $fail -eq 0 ]

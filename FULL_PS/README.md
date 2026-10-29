# FULL_PS - all five receiver algorithms on Cortex-A9

Target: AllAboutFPGA EDGE Z7-10, XC7Z010CLG400-1, board revision A.0.

```text
Host encoder -> UART -> ARM: helical -> Viterbi -> block deinterleaver
                         -> Reed-Solomon -> derandomizer -> UART -> host
```

`sw/src/receiver.c` implements a 64-state hard-decision, K=7 Viterbi decoder
with puncturing and full terminated traceback, byte deinterleaving, and
Berlekamp-Massey/Chien/Forney RS decoding. It preserves tie-breaking and failure
behavior of `model/ldacs_ref.py`. Static decision history supports 22,016 steps;
no heap allocation is used. GF and convolutional tables initialize at boot.
The existing C helical and PRBS functions are retained byte-for-byte.

`hw/vivado/create_project.tcl` generates **PS7 + DDR + fixed IO only**, so the
bitstream/preset used for boot contains no decoder accelerator or AXI DMA.
The firmware does not read or write decoder/DMA addresses in FULL_PS builds.

## Functional validation

```powershell
python scripts/validate_c_receiver.py
python scripts/validate_software_modes.py
```

The first command compiles the actual receiver C with host GCC and checks all
five intermediate buffers across 24 mode/error combinations, plus nine direct
RS symbol-error cases. These tests include correction and failure paths.
Host test times must not be used as Cortex-A9 benchmark measurements.

## Shared experiment boundary

These variants implement the same **five-stage receiver** as the original project.
The transmitter remains the Python host encoder; RF/OFDM functions are outside the
experiment. In FULL_PL, the ARM still handles UART, register configuration and DMA
transport; none of the five decoding algorithms execute on ARM. FULL_PS uses one
Cortex-A9 core, with no PL decoder or DMA. The original project at the parent
folder remains the HYBRID baseline.

All three benchmark firmware images use the same Cortex-A9 compiler flags,
uncached DDR policy, input frames, frame parameters and protocol. Keep the same
CPU and PL frequencies when making the primary architecture comparison. This is
a controlled baseline, not a claim that uncached ARM software is the fastest
possible CPU implementation. A later cache/NEON/dual-core study must be reported
as a separate configuration.

## Build and boot

Run commands from this variant's directory. Vivado/Vitis 2022.2 is the original
project's tool version; the new Vivado flows still require validation there.

```powershell
python -m pip install -r requirements.txt
Push-Location hw/vivado
vivado -mode batch -source create_project.tcl
vivado -mode batch -source build.tcl
Pop-Location
python build_firmware.py
xsdb.bat boot_firmware.tcl
```

`build_firmware.py --gcc C:/path/to/arm-none-eabi-gcc.exe` selects a compiler
explicitly. Use the **same compiler** for all three research images. Firmware is
linked into DDR at 0x01000000. The boot flow initializes the board through its
checked-in EDGE preset before programming and downloading firmware. Variant
build products live under this variant; they do not overwrite the hybrid build.

## Board use

```powershell
python host/board_client.py trace --port COM5 --mode qpsk_1_2 --message "Research frame" --output results/trace.json
python host/board_client.py benchmark --port COM5 --mode all --iterations 20 --warmups 2 --batches 5 --seed 91 --output results/board.json
python server.py --port COM5 --http-port 8001
```

The optional console is at http://127.0.0.1:8001. Close other serial-port clients
before connecting. Trace responses contain the architecture ID and five actual
board buffers, each checked against the complete Python decoder. Benchmark
responses contain the architecture ID, raw counters, per-frame CRC failure
count, and the final payload. The client rejects a different architecture's
firmware. It never substitutes a software result if hardware is unavailable.

Trace captures can involve extra PL executions to return intermediate data;
**use the one-pass benchmark command for performance comparisons**. Its decoder
measurement excludes UART, output-buffer copying and per-frame CRC checking.
It includes DMA/reset/configuration overhead for architectures using PL. Raw PL
pipeline timing is separately available for examining the accelerator itself.

Stage latencies in a streaming pipeline overlap and must not be added to obtain
total latency. Host UART batch wall time includes transport, warmups, all
repetitions and CRC checks; it is reported separately. The ARM global timer uses
CPU/2 ticks. PL stage counters use FCLK0 ticks. Both frequencies are derived
from live SLCR clock configuration and the nominal 33.333333 MHz PS oscillator;
this is not an independent oscillator calibration.

## Interpretation

The copied model retains the original SPEC-CHECK assumptions: helical permutation,
frame layout, PRBS seed/polynomial and coding parameters have not been established
by independent LDACS vectors. Agreement between implementations validates this
experiment's consistency, not standards conformance. Modulation mode names select
coding/frame profiles; no radio modulation/demodulation is performed here.

See `../BENCHMARKS/README.md` for the three-way research procedure and comparison
commands. There are **no new real-board performance results** yet. Vivado power
reports, when generated, are estimates rather than measured board power.

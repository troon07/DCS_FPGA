# Three-way LDACS receiver partition study

The preserved parent project is HYBRID. `FULL_PL` and `FULL_PS` are independent
source/build trees inside that repository. Original files have not been edited;
`baseline_manifest.json` records SHA-256 hashes of their exact working bytes.
The copied Python reference models and board definitions use identical bytes.

| Receiver block | HYBRID | FULL_PL | FULL_PS |
|---|---|---|---|
| Helical deinterleaver | ARM PS | FPGA PL | ARM PS |
| Viterbi decoder + bit packing | FPGA PL | FPGA PL | ARM PS |
| Block deinterleaver | FPGA PL | FPGA PL | ARM PS |
| Reed-Solomon decoder | FPGA PL | FPGA PL | ARM PS |
| PRBS derandomizer | ARM PS | FPGA PL | ARM PS |

UART transport and configuration run on ARM in every case. The host encoder
stays on the PC. FULL_PS is a single-core implementation. All three use the
same hard-decision FEC chain, assumed LDACS constants, eight mode layouts and
no-cache firmware policy. Decoder correctness is checked before any number is
eligible for the comparison table.

## 1. Validate before hardware runs

From the repository root:

```powershell
python FULL_PS/scripts/validate_c_receiver.py
python FULL_PL/scripts/validate_pl.py
python BENCHMARKS/test_protocol.py
```

The C test requires host GCC; the RTL test requires Icarus Verilog. Neither
provides real-board latency. `verify_baseline.py` checks that the original
files and copied reference models/board files remain unchanged.

## 2. Build all images with one toolchain

Follow each variant README to create and implement its Vivado project. Use the
same part, board preset and requested 70 MHz FCLK0 for the primary study. Confirm
the **actual** clock and all setup/hold checks in routed reports; Vivado may
quantize the requested frequency. `build.tcl` rejects negative setup/hold slack
and exports an XSA only after that check. Review implementation warnings too.

Build firmware using a single selected compiler:

```powershell
python FULL_PS/build_firmware.py --gcc C:/path/to/arm-none-eabi-gcc.exe
python FULL_PL/build_firmware.py --gcc C:/path/to/arm-none-eabi-gcc.exe
python BENCHMARKS/hybrid/build_firmware.py --gcc C:/path/to/arm-none-eabi-gcc.exe
```

The third image is **new hybrid benchmark firmware** that uses the original
hybrid bitstream. It removes trace replay from timed benchmark transactions and
provides the same protocol and timing boundary as the new variants. The original
`sw/uart_bridge.elf`, original console and source firmware remain untouched.
The hybrid benchmark boot file uses the original board-generated PS preset and
bitstream. Each generated `sw/firmware_build.json` records compiler, flags,
source hashes and ELF hash. Keep those metadata files with experimental records.

## 3. Run the same experiment on the same physical board

Close all other COM5 clients. Run the following sequentially, from the repository
root, with the board connected and powered. Rebuild the original hybrid bitstream
first if its local image does not match the preserved source. Use a consistent
board power supply and record ambient conditions for power/thermal studies.

```powershell
xsdb.bat BENCHMARKS/hybrid/boot_firmware.tcl
python BENCHMARKS/run_board.py --variant HYBRID --port COM5 --mode all --iterations 20 --warmups 2 --batches 5 --seed 91 --output BENCHMARKS/results/hybrid.json

xsdb.bat FULL_PL/boot_firmware.tcl
python BENCHMARKS/run_board.py --variant FULL_PL --port COM5 --mode all --iterations 20 --warmups 2 --batches 5 --seed 91 --output BENCHMARKS/results/full_pl.json

xsdb.bat FULL_PS/boot_firmware.tcl
python BENCHMARKS/run_board.py --variant FULL_PS --port COM5 --mode all --iterations 20 --warmups 2 --batches 5 --seed 91 --output BENCHMARKS/results/full_ps.json
```

This default records 100 measured frames per mode/architecture, with two warmups
per batch. Repeat experiments in reversed/randomized architecture order to check
order and thermal effects. For additional independent data sets, vary `--seed`
consistently across all three architectures and preserve each set separately.
`--board-label` can identify the actual physical board. The firmware ID in every
response must match the requested architecture; otherwise the run is rejected.
A missing board, wrong image, timeout or DMA failure is an error, never a model
fallback. The scripts do not claim that downloading firmware proves hardware
correctness: output validation must also succeed.

## 4. Compare captured evidence

```powershell
python BENCHMARKS/compare.py BENCHMARKS/results/hybrid.json BENCHMARKS/results/full_pl.json BENCHMARKS/results/full_ps.json --output BENCHMARKS/results/comparison.csv
```

This creates CSV and Markdown tables of mean/minimum/maximum decoder latency,
payload throughput, stage latencies, speedup relative to FULL_PS, and available
routed LUT/FF/BRAM/DSP/slack metrics. Missing routed metrics remain empty.
It refuses mismatched frames, seeds, modes, clock settings, compiler versions,
missing image metadata and unsuccessful board responses. All raw batch records
remain in the input JSON files. Local hashes document the intended build; matching
the booted image also depends on following the boot procedure. These are not
cryptographic device attestation.

If the application has a specified frame deadline, pass `--deadline-us VALUE`.
This reports whether **all observed decoder calls** met that deadline. The
largest observed latency is not a worst-case execution-time proof, and a
receiver-only measurement does not establish end-to-end RF system real time.

## Measurement boundaries

* **Decoder latency:** one complete five-stage frame decode, measured by the
  ARM global timer. It includes DMA programming, decoder reset and DMA wait for
  HYBRID/FULL_PL. Input is already resident on board. UART, final output copy and
  CRC checks are excluded. The FULL_PL input staging copy is transport work.
* **Stage latency:** PS stages use the global timer; PL stages use FCLK0 counters
  spanning first accepted input through last accepted output. Stage clocks and
  raw tick sums are retained; streaming/backpressure effects are included.
* **PL pipeline:** a separate whole-accelerator counter, absent for FULL_PS.
  In FULL_PL it includes all five stages; in HYBRID it includes three stages.
  These different scopes are explicitly labeled and are not the primary speedup
  comparison. Streaming stage times overlap; never add them to obtain latency.
* **UART batch wall time:** host measurement including input/output transport,
  warmups, repetitions and CRC checks. Do not divide a multi-frame decoder time
  by the single trace wall time or label UART timing as internal FPGA speed.
* **Correctness:** every measured iteration checks CRC32 against the original
  payload, and the final frame is compared byte-for-byte by the host. Trace mode
  additionally compares every intermediate stage to the full Python reference.
* **Clock frequency:** live SLCR PLL/divider configuration with nominal board
  reference 33,333,333 Hz; global timer at CPU/2, FCLK0 from its configured PLL.
  Reference: https://github.com/Xilinx/u-boot-xlnx/blob/master/drivers/clk/clk_zynq.c
  Clock counts are measured; the oscillator is not independently calibrated.
* **Resources:** use each image's own routed Vivado reports. `power_estimate.rpt`
  is a tool estimate. Actual watts, energy per frame and temperature require
  external measurements and are intentionally absent from runtime results.

## Current status and limitations

Functional simulations and host C tests can be performed here; routed FPGA
validation and physical-board measurements remain pending. No benchmark result
files or performance claims are manufactured. Read `VALIDATION.md` for completed
checks. Independent LDACS conformance vectors remain necessary because all
variants share the original SPEC-CHECK constants. This is a receiver partition
study, without RF, OFDM synchronization, channel estimation or demapping.

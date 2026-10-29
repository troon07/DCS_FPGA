# Completed validation - 29 October 2026

These are functional and build checks, **not FPGA-board performance results**.

| Check | Result |
|---|---|
| Preserved hybrid source hashes | All 81 original tracked files unchanged |
| Shared Python model and board definitions | Exact copies in both variants |
| Reused Viterbi / bit packer / block deinterleaver / RS RTL | Exact copies of baseline cores |
| Full PS receiver C against Python | 24 frame cases: eight modes at BER 0, 0.01, 0.035; all five stages matched |
| Direct C RS tests against Python | Nine cases with 0..8 symbol errors, covering correction and failure |
| Full PL RTL against Python | 15 cases, including all eight modes, noisy frames, RS correction/failure and all trace taps |
| RTL stream handshakes | Random input gaps and output backpressure exercised |
| Protocol and comparison tests | 11 tests passed, including fragmented responses, wrong architecture, bad metadata, CRC failures, timeouts and incompatible captures |
| ARM cross-compilation | HYBRID benchmark, FULL_PL and FULL_PS ELFs built successfully without compiler/linker warnings |
| Firmware partition inspection | FULL_PL ELF has no C receiver algorithms; FULL_PS ELF contains all C receiver stages |
| Local consoles | Both serve UTF-8 HTML and correctly return an error when hardware is absent |
| Browser JavaScript | Syntax checks passed for both consoles |

Compiler: xPack Arm GNU GCC 15.2.1. RTL simulator: Icarus Verilog 13.0.
Per-case functional logs and vectors are under each variant's ignored `build/`
folder. ELF/build metadata are under each image's ignored `sw/` outputs. The
machine-readable summary beside this file records the three built ELF hashes.

## Still pending

Vivado is unavailable on this machine, and serial-port enumeration found no
ports. Therefore the new Vivado flows, FPGA fit, routed timing, utilization,
physical board boot, board correctness, actual latency/throughput and the
three-way comparison remain unverified. Simulations do not establish any of
those hardware results. Build and run the commands in `README.md` on the
Vivado/board setup before making performance claims in the paper.

The existing LDACS SPEC-CHECK assumptions are retained in all implementations.
Independent specification-derived test vectors are still required for a
standards-conformance claim.

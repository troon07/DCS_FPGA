# Project Context: DCS_FPGA (FULL_PL Variant)
- **Target**: AllAboutFPGA EDGE Z7-10 (`XC7Z010CLG400-1`, rev A.0), Vivado/Vitis 2022.2.
- **Pipeline**: Host -> UART/ARM -> DDR -> AXI DMA (`0x40400000`) -> PL (`0x40000000`: `helical_deint.v` -> Viterbi -> bit packer -> byte deinterleaver -> RS -> `prbs_derand.v`) -> AXI DMA -> DDR -> ARM/UART -> Host.
- **Unchanged RTL**: Viterbi, bit packer, byte deinterleaver, generated RS RTL.
- **New/Modified RTL**: `helical_deint.v` (24-row inverse permutation, 1-bit/RAM location, registered column counts replacing div-by-24), `prbs_derand.v` (bytewise PRBS XOR, advances on accepted bytes), AXI-Lite wrapper (`VERSION=0x46504C31` at `0x24`, Trace at `0x28` [0..4], Helical latency at `0x40`, PRBS latency at `0x44`, Coded bits at `0x4C`).
- **Hard Rules**:
  1. Never modify `HYBRID` (parent folder) or `FULL_PS` baselines, compiler flags, uncached DDR policy (`0x01000000`), or clock frequencies.
  2. Never add `set_false_path` or `set_multicycle_path` to suppress timing failures.
  3. Never read entire `build/*.rpt` or `.log` files into context; use targeted `Select-String` / `grep` for `Slack`, `VIOLATED`, `ERROR`, or specific failing path endpoints.

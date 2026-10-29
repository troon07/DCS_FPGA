# LDACS Real-Hardware Bring-Up Summary

**Outcome: hardware integration validated, spec conformance NOT validated.**

This run validates the PS↔PL datapath, AXI DMA operation, uncached DDR handling,
UART framing, timing closure, and XC7Z010 resource fit. The zero-error loopback
uses the same assumed constants in the encoder and decoder, so it does not test
the correctness of those constants against the LDACS specification.

## Confirmed hardware target

- The physical JTAG target is `xc7z010`.
- The Vivado target is `allaboutfpga.com:edgez7_10:part0:1.0` / `xc7z010clg400-1`.
- The board references are the [EDGE ZYNQ SoC FPGA Development Board User Manual](https://allaboutfpga.com/edge-zynq-soc-fpga-development-board-user-manual/) and the official [AllAboutFPGA EDGE board-file repository](https://github.com/AllAboutFPGA/EDGE-FPGA-Kit-Board-Files).
- The local `board_details/edgeZ7_10/A.0` copies of `board.xml`, `preset.xml`, and `part0_pins.xml` were compared with the official repository versions and match exactly after line-ending normalization.
- The Vivado batch script sets `board.repoPaths` to the local `board_details` directory before selecting the EDGE Z7-10 board part, so the build uses that verified definition directly.
- PS UART0 is MIO 14–15 at 115200 baud; Windows enumerates the board USB-UART as `COM5`.

## Changes made

- Retargeted the Vivado project and XSDB boot script from EDGE Z7-20 / XC7Z020 to EDGE Z7-10 / XC7Z010.
- Kept the paper's decoder partition: ARM PS runs helical deinterleaving and PRBS derandomizing; FPGA PL runs Viterbi, block deinterleaving, and Reed-Solomon decoding.
- Updated the bridge for PS UART0 (`0xE0000000`) and added explicit block-design IP generation to the Vivado batch flow.
- Lowered the PL clock from 75 MHz to 70 MHz after the XC7Z010 75 MHz build missed setup timing by 0.004 ns.
- Probed PS memory after generated `ps7_init.tcl`: OCM (`0xFFFC0000`) aborts, while DDR (`0x00100000`) reads/writes correctly.
- Moved the ARM firmware image to DDR at `0x01000000`; DMA buffers remain at their lower DDR addresses.
- Removed decoder fallback output when hardware does not respond and replaced status resource placeholders with routed Vivado values.

## Build result

- Cortex-A9 firmware: `sw/uart_bridge.elf` built successfully.
- Firmware ELF size: 70,388 bytes.
- XC7Z010 synthesis, implementation, bitstream generation, and XSA export completed successfully.
- Vivado PS configuration request: 70 MHz; implemented clock from the timing
  report: 71.429 MHz (14.000 ns period).
- Timing: WNS `0.233 ns`, TNS `0.000 ns`, zero setup/hold failing endpoints.
- Filtered Vivado `ERROR`/`CRITICAL WARNING` output: none.

Parsed timing report line:

```text
0.233        0.000                      0                21326        0.050        0.000                      0                21326        5.750        0.000                       0                  6577
```

Parsed clock report line:

```text
clk_fpga_0  {0.000 7.000}      14.000          71.429
```

Parsed utilization report lines:

```text
| Slice LUTs      | 11270 | 0 | 0 | 17600 | 64.03 |
| Slice Registers |  5990 | 0 | 0 | 35200 | 17.02 |
| Block RAM Tile  |  50.5 | 0 | 0 |    60 | 84.17 |
| DSPs            |    1 | 0 | 0 |    80 |  1.25 |
```

| Resource | Used | Available | Utilization |
| --- | ---: | ---: | ---: |
| Slice LUTs | 11,270 | 17,600 | 64.03% |
| Slice registers | 5,990 | 35,200 | 17.02% |
| Block RAM tiles | 50.5 | 60 | 84.17% |
| DSPs | 1 | 80 | 1.25% |

## Real board execution

1. XSDB detected `xc7z010` through JTAG.
2. The XC7Z010 bitstream was programmed successfully.
3. Generated PS initialization ran, and the DDR-resident ARM bridge was loaded and started.
4. A real transaction completed:

   ```text
   PC UART -> ARM PS helical deinterleaver -> FPGA PL decoder ->
   ARM PS PRBS derandomizer -> PC UART
   ```

5. Input: `HARDWARE INTEGRATION VALIDATION COM5`.
6. Hardware-returned output: `HARDWARE INTEGRATION VALIDATION COM5`.
7. The transaction used QPSK 1/2, 9,768 coded bits, 4,884 trellis steps,
   six RS codewords, RS N=101, RS K=91, and a 546-byte frame payload.
8. The trace firmware returns the real helical-deinterleaver, Viterbi,
   block-deinterleaver, RS-decoder, and final derandomizer buffers. A QPSK 1/2
   transaction matched the full software decoder at all five stages with zero
    mismatches, zero RS corrections, and zero RS failures.

## Real per-block performance instrumentation

TRC3 measures the first accepted input through the final accepted output of
each block with the board's free-running 71,428,497 Hz PL clock. A real QPSK
1/2 COM5 validation transaction produced:

| Board block | Domain | Cycles | Latency |
| --- | --- | ---: | ---: |
| Helical deinterleaver | Zynq ARM PS | 484,858 | 6,788.019 us |
| Viterbi decoder | XC7Z010 FPGA PL | 34,117 | 477.638 us |
| Block deinterleaver | XC7Z010 FPGA PL | 11,348 | 158.872 us |
| Reed-Solomon decoder | XC7Z010 FPGA PL | 1,758 | 24.612 us |
| PRBS derandomizer | Zynq ARM PS | 22,684 | 317.576 us |
| Complete FPGA pipeline | XC7Z010 FPGA PL | 35,876 | 502.265 us |

The complete FPGA counter measures the streaming pipeline as a whole, so its
latency is not the sum of independently overlapping stage latencies. The COM5
trace wall clock remains separate because it includes UART transport and three
hardware passes.

Current routed per-hierarchy Vivado results:

| Hierarchy | LUT | FF | BRAM | DSP | Worst setup slack |
| --- | ---: | ---: | ---: | ---: | ---: |
| Viterbi decoder | 5,155 | 1,078 | 44 | 0 | +1.430 ns |
| Block deinterleaver | 118 | 74 | 1 | 0 | +6.277 ns |
| Reed-Solomon decoder | 2,783 | 653 | 0.5 | 0 | +0.233 ns |
| Complete decoder IP | 8,428 | 2,198 | 45.5 | 1 | +0.233 ns |

The frontend performance dropdown displays these routed reports together with
the latest real host, PS, and PL runtime measurements. It displays unavailable
when a report or hardware measurement does not exist; it does not substitute
paper values.

## Parameter cross-check boundary

- `RS(101,91), t=5, 10 check symbols, consistent with Section IV-D ranges and forced by K=7 per-codeword termination.`
- The helical permutation, `HELICAL_ROWS`, block-interleaver geometry, and PRBS
  seed/polynomial remain `SPEC-CHECK` assumptions and are not testable by this
  loopback. Their source markers were retained unchanged.

## Full-mode hardware correction

- An eight-mode COM5 sweep exposed an undersized top-level Viterbi history
  buffer: the decoder was limited to 14,656 steps although `64qam_2_3` needs
  19,536 and `64qam_3_4` needs 21,978.
- The top-level capacity was raised to 22,016 steps. The decision history was
  banked into 512x64 memories so Vivado maps it efficiently to native RAMB36
  geometry and the design still fits XC7Z010.
- The Vivado build script now resets block-design/module-reference synthesis
  runs so RTL changes cannot silently reuse a stale decoder checkpoint.
- After rebuilding and programming, all eight modes passed real COM5 hardware
  transactions with exact payload recovery, zero byte/bit mismatches, zero RS
  failures, and exact agreement with the full software receive chain.

## Generated artifacts

- `hw/vivado/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit`
- `hw/vivado/build/ldacs_zed.xsa`
- `hw/vivado/build/timing.rpt`
- `hw/vivado/build/utilization.rpt`
- `sw/uart_bridge.elf`

## Remaining work

- **hardware integration validated, spec conformance NOT validated.**
- The zero-error transaction confirms the real hardware path works. Independent
  specification-derived vectors are still required to validate the marked
  constants; loopback cannot provide that evidence.

## UI and software-model cross-check

- The Transmit and Latest Result pages were simplified to show measured COM5
  results, real hardware counters, the routed XC7Z010 utilization, and the
  observed PS/PL transaction path. Paper timing/throughput tables, generated
  constellation data, SNR controls, and artificial error injection were removed
  from the live UI.
- Each hardware transaction now also runs the complete software receive chain
  against the exact encoded frame sent to COM5 and reports hardware-versus-
  software byte agreement separately from the hardware measurement.
- All eight zero-error software encode/decode modes passed with zero payload
  mismatches and zero RS failures.
- A real eight-mode COM5 trace sweep passed every mode. Each transaction had
  zero final payload mismatches, zero RS failures, and zero mismatches at all
  five board-versus-software decoder stages. Observed traced round-trip times
  ranged from approximately 1.93 s to 6.04 s because the full intermediate
  buffers are returned over 115200-baud UART.
- The software comparison shares the same `SPEC-CHECK` constants and therefore
  confirms implementation consistency only.
- **hardware integration validated, spec conformance NOT validated.**

# DPR receiver partition study on EDGE Z7-10

Three separate source projects extend the existing static receiver experiments.
The original project, `FULL_PL`, `FULL_PS` and `BENCHMARKS` are preserved.

| Project | ARM receiver stages | Reconfigurable receiver stages |
|---|---|---|
| `HYBRID` | Helical deinterleaving and PRBS derandomization | Viterbi, bit packing, block deinterleaving, RS |
| `FULL_PL` | None; ARM handles transport and control | All five receiver stages |
| `FULL_PS` | All five receiver stages | None; blank/diagnostic modules occupy the slot |

**FULL_PS does not reconfigure the processor.** It is the CPU receiver running
on a DPR-capable platform. Its experiment swaps between a blank module and a
non-decoding diagnostic module. The ARM command loop serializes switching and
decoding; concurrent CPU decoding during PCAP transfer is not implemented.

Every project contains its own board files, Python encoder/reference receiver,
ARM firmware, RTL, Vivado flow, packaging tools, host client and tests. Every
hardware source tree contains the same four pin-compatible modules:

| Module | ID | Function |
|---|---:|---|
| `hybrid` | 0 | Three-stage PL receiver core |
| `full_pl` | 1 | Complete five-stage PL receiver |
| `blank` | 2 | No decoding; CPU-reference slot image |
| `anchor` | 3 | Non-decoding diagnostic/heartbeat image |

The host transmitter stays on the PC, as in the static experiments. RF, OFDM
synchronization, channel estimation and demapping remain outside this study.

## Architecture

```text
ARM / DDR / UART / AXI DMA / FCLK / resets  (static)
                   |
         static AXI proxy + isolation + build identity
                   |
         rp_decoder (one reconfigurable partition)
              hybrid / full_pl / blank / anchor
```

The static shell accepts independent AXI write address/data channels, blocks
new frame traffic while isolated, rejects accesses to the isolated RP, and
refuses isolation while a frame or RP read transaction is active. RP clocks
remain static. A local reset is held across loading and restart; no global PL
reset is issued by the partial loader. Its identity is checked before releasing
the data interfaces.

ARM uploads verified partial images into four separate DDR cache slots starting
at `0x03000000`, each at most 8 MiB. They do not overlap firmware or decoder DMA
buffers. A subsequent switch uses DevCfg/PCAP from cached DDR. The firmware
checks DMA quiescence, isolates, transfers, polls completion/errors with a
timeout, verifies module identity, and restarts. Failed loads leave the RP
isolated/reset. Recovery may require rebooting the full platform.

## 1. Validate the sources

From the repository root, with GCC and Icarus Verilog installed:

```powershell
python DPR/verify_preserved.py
python DPR/HYBRID/scripts/validate_rtl.py
python DPR/FULL_PL/scripts/validate_rtl.py
python DPR/FULL_PS/scripts/validate_c_receiver.py
python DPR/FULL_PL/tests/test_host.py
python DPR/FULL_PL/tests/test_pcap.py
python DPR/tests/test_compare_six.py
```

RTL validators also accept `--iverilog` and `--vvp` executable paths. The static
shell test can be run separately:

```powershell
iverilog -g2012 -s tb_shell -o shell_test.vvp DPR/FULL_PL/tests/tb_shell.v DPR/FULL_PL/tests/mock_rp.v DPR/FULL_PL/hw/static/dpr_shell.v
vvp shell_test.vvp
```

This test models an RP identity change to exercise isolation/reset logic. It
does **not** simulate the physical configuration engine or validate a partial
bitstream. PCAP register-fixture tests execute the actual loading routine but
likewise do not establish hardware functionality or timing.

## 2. Build one common image family in Vivado

Use the same installed Vivado version and compiler for all six experiments.
The starting flow targets Vivado 2022.2 and `xc7z010clg400-1` with the local
EDGE Z7-10 preset. Confirm DFX support in the installed tools.

Recommended: build the family once under `DPR/FULL_PL`, then use its locked
static implementation for all three ARM variants:

```powershell
Push-Location DPR/FULL_PL/hw/vivado
vivado -mode batch -source create_project.tcl
vivado -mode batch -source build.tcl
Pop-Location
python DPR/FULL_PL/scripts/package_images.py
```

Each project also has the complete build flow if an independent family is
needed. **Never mix partial files from separate builds.** Each project creation
generates a new build token in the static shell. A family includes that token,
full/partial image hashes and its locked-static checkpoint hash.

The implementation synthesizes the static shell as a black box around the RP,
synthesizes each RM out of context, and implements FULL_PL first. It then locks
the static routing and implements the other modules against that checkpoint.
The flow checks timing/DRC and runs `pr_verify` before accepting the family.
Reports are generated separately for every configuration. Power reports are
Vivado estimates, not measured board power.

### Floorplan status

`floorplan.tcl` computes a **starting candidate from actual device site names**.
It leaves a top-right SLICE region and ten BRAM36 sites for static logic and
reserves the remainder for the largest RM. This is not a verified XC7Z010 DFX
floorplan. Resource pressure, partition-pin routing or timing may require changes
in Vivado. Override it with `hw/vivado/floorplan_override.xdc`, resizing the
already-created `pblock_decoder`. DRC/timing/compatibility failures must be fixed
before board experiments. Packaging refuses an incomplete/failed implementation.

The RP reserves capacity for the largest module even when blank. Do not claim
that loading FULL_PS releases that physical region for arbitrary static logic.

## 3. Build the three ARM images

```powershell
python DPR/HYBRID/build_firmware.py
python DPR/FULL_PL/build_firmware.py
python DPR/FULL_PS/build_firmware.py
```

Pass `--gcc C:/path/to/arm-none-eabi-gcc.exe` to select the same compiler used
for the static study. Firmware/build metadata include the PCAP include source.
All three retain the static experiment's single-core, I/D-cache-disabled policy.

## 4. Capture real DPR measurements

Run sequentially with the same physical board and COM port. The optional boot
argument selects the shared image-family directory; the ARM ELF is always taken
from the project whose boot script is invoked.

```powershell
$family = (Resolve-Path DPR/FULL_PL/hw/vivado/build/dfx).Path

xsdb.bat DPR/HYBRID/boot_firmware.tcl $family
python DPR/HYBRID/host/dpr_client.py --images "$family/images.json" --port COM5 --switches 3 --mode all --iterations 20 --warmups 2 --batches 5 --seed 91 --output DPR/results/hybrid.json

xsdb.bat DPR/FULL_PL/boot_firmware.tcl $family
python DPR/FULL_PL/host/dpr_client.py --images "$family/images.json" --port COM5 --switches 3 --mode all --iterations 20 --warmups 2 --batches 5 --seed 91 --output DPR/results/full_pl.json

xsdb.bat DPR/FULL_PS/boot_firmware.tcl $family
python DPR/FULL_PS/host/dpr_client.py --images "$family/images.json" --port COM5 --switches 3 --mode all --iterations 20 --warmups 2 --batches 5 --seed 91 --output DPR/results/full_ps.json
```

The client stages both required partials once, then performs actual PCAP round
trips: `blank -> decoder` for accelerated projects, and `anchor -> blank` for
FULL_PS. Every restoration is followed by a verified QPSK payload decode.
The full-mode steady-state sweep follows, using the same deterministic frames,
warmups and repetitions as the static study. Change `--board-label` to identify
the physical board when needed, consistently across all captures.

UART image staging may take minutes at 115200 baud; its wall time is recorded
and excluded from cached-image reconfiguration time. Do not interrupt an upload:
an incomplete UART payload requires restarting the firmware. This implementation
uses unencrypted PCAP images, not secure-boot/encrypted partial-image loading.

## Measurement meanings

* Decoder mean/min/max, stage counters and payload throughput use the same
  timing boundaries as the existing static benchmark. DMA/control overhead is
  included in whole decoder time for accelerated implementations.
* `isolation`, `pcap`, `restart` and `unavailable` are actual global-timer
  measurements. `total` spans quiescence checking through successful restart.
* `precheck` measures cached-image validation before isolation. `service_total`
  includes that validation plus the switch, so its CPU cost is not hidden.
* UART staging and host control wall time are separate. Host control wall time
  also includes protocol/status transactions. It is not pure PCAP throughput.
* No overlapping frame arrivals are injected during switching. Frame loss,
  queue occupancy, concurrent CPU fallback and traffic-dependent scheduling
  have not been implemented or measured by these scripts.
* CPU-only decoder execution remains in PS. Its slot downtime is not proof that
  the processor hardware was unavailable. The serialized command loop pauses
  decoding while it executes the load routine.

## 5. Compare all six configurations

First collect the three static JSON files using `BENCHMARKS/README.md` with the
same compiler, clocks, board label, seed, modes, warmups and repetition settings.

```powershell
python DPR/compare_six.py BENCHMARKS/results/hybrid.json BENCHMARKS/results/full_pl.json BENCHMARKS/results/full_ps.json DPR/results/hybrid.json DPR/results/full_pl.json DPR/results/full_ps.json --output DPR/results/comparison.csv
```

CSV and Markdown outputs keep steady-state decoding and switching separate.
They include available routed resource/slack measurements, speedup against
static FULL_PS, and matched static-versus-DPR decoder overhead. Missing build
metrics remain empty. Missing captures, wrong architecture/protocol, incompatible
clocks/frames/compiler settings or failed post-switch decoding are rejected.

Optional `--frames-per-switch-roundtrip N` computes an amortized workload cost
using both transitions' measured `service_total`. This is a derived scenario,
not another hardware observation. It excludes first-time UART image staging.
There are no manufactured performance values or placeholder benchmark captures.

## Current limitations

Read `VALIDATION.md` for completed checks. Vivado execution, floorplan legality,
fit, routing, timing closure, partial-bitstream generation/compatibility, real
PCAP loading and board benchmarks remain pending. The included scripts are
source implementations, not hardware-validated DPR images.

All projects retain the existing LDACS `SPEC-CHECK` assumptions. Agreement among
implementations is not independent LDACS standards conformance. Image hashes and
build tokens prevent accidental family mixing; they are not device attestation
or authentication against a malicious image/manifest.

## Primary implementation references

* [AMD UG909: standard DFX implementation flow](https://docs.amd.com/api/khub/documents/aFtTMbStto75TDahM0xQEg/content)
* [AMD UG909: reconfigurable-region floorplanning](https://docs.amd.com/r/en-US/ug909-vivado-partial-reconfiguration/Create-a-Floorplan-for-the-Reconfigurable-Region)
* [AMD UG585: PCAP configuration sequence](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Configure-the-PL-via-PCAP-Bridge-Example)
* [Xilinx DevCfg register definitions, 2022.2](https://github.com/Xilinx/embeddedsw/blob/xilinx_v2022.2/XilinxProcessorIPLib/drivers/devcfg/src/xdevcfg_hw.h)

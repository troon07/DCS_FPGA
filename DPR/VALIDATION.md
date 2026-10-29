# DPR validation - 29 October 2026

All results below are source, functional simulation or cross-compilation checks.
**No physical-board DPR event or benchmark has been performed.**

| Check | Result |
|---|---|
| Existing project preservation | All 159 pre-existing source files unchanged |
| Common hardware and reference model copies | Exact matching DPR shells/RMs and shared model |
| HYBRID through static DPR shell | 13 successful vector simulations, all eight modes plus noisy/trace cases |
| FULL_PL through static DPR shell | 15 successful vector simulations, all eight modes plus noisy/trace cases |
| Final static CSR regression | Quick HYBRID and FULL_PL pipelines passed after diagnostic-ID addition |
| Static isolation/AXI proxy | Split writes, forwarding, active-frame rejection, reset, masked/raw identity and generation passed |
| Compatible module interfaces | All four RMs compile against the same shell interface |
| FULL_PS C receiver | 24 mode/error combinations matched Python at all five stages |
| Direct RS C checks | Nine cases covering 0..8 symbol errors, correction and failure |
| DPR host protocol/image packaging | Nine unit tests passed for each of the three project clients |
| Actual PCAP driver with mocked registers | Eight native-C tests passed: programming sequence, no global PL reset, queue/init errors, interrupt errors, timeout, fault latch |
| Six-way comparison | Four tests passed; mislabeled static responses and missing post-switch checks are rejected |
| ARM firmware | All three final images cross-compiled successfully with xPack Arm GNU GCC 15.2.1 |
| Python/Tcl | Python syntax and Tcl source completeness checked |

RTL simulator: Icarus Verilog 13.0. Generated vectors, simulator logs, native
fixture libraries and ELF files remain in ignored build/output locations.
`validation_summary.json` records case names and exact final ARM ELF hashes.

## Not yet validated

Vivado is unavailable here, and no serial ports were detected. Therefore:

* The Tcl files have not been executed by Vivado. Tcl completeness is not a
  validation of Vivado command semantics or project generation.
* The device-derived Pblock is a starting candidate. Fit, legal partition
  boundaries, resource placement, routing and timing closure remain unproven.
* No real `pr_verify` result, partial bitstream or packaged hardware image has
  been generated for these DPR projects.
* Register fixtures do not model the physical PCAP engine, configuration frames,
  static-routing preservation, hardware reset/startup, or board power.
* No real reconfiguration latency, downtime, decoder latency/throughput, power,
  energy or six-way board comparison is claimed.

Follow `README.md` on the Vivado/board machine. Fix any floorplan, DRC or timing
failures before packaging or programming. All variants also retain the original
unverified LDACS SPEC-CHECK constants; independent standards vectors are needed.

# DPR FULL_PL receiver project

Target: EDGE Z7-10, XC7Z010CLG400-1, local A.0 board preset.

All five receiver stages execute in the dynamic module. ARM provides UART, DMA transport, control and PCAP loading.

This folder is a separate source project with its own firmware, reference model,
board definitions, complete common-shell/multi-RM hardware flow and host tools.
Its four compatible modules are `hybrid`, `full_pl`, `blank` and `anchor`.
The default boot image and expected decoder identity match this project's name.

## Standalone build

Run these from this project directory, with Vivado and an Arm GNU compiler:

```powershell
Push-Location hw/vivado
vivado -mode batch -source create_project.tcl
vivado -mode batch -source build.tcl
Pop-Location
python scripts/package_images.py
python build_firmware.py
xsdb.bat boot_firmware.tcl
python host/dpr_client.py --port COM5 --switches 3 --mode all --iterations 20 --warmups 2 --batches 5 --seed 91 --output results/board.json
```

Pass `--gcc C:/path/to/arm-none-eabi-gcc.exe` to select the compiler explicitly.
`hw/vivado/floorplan.tcl` is a starting device-derived candidate; it has not been
validated in Vivado here. Timing, fit, DFX DRC and `pr_verify` must succeed before
images can be packaged or treated as usable benchmark hardware.

## Local functional checks

```powershell
python scripts/validate_rtl.py
python scripts/validate_shell.py
python tests/test_host.py
python tests/test_pcap.py
```

Icarus scripts accept explicit `--iverilog` and `--vvp` paths. Host tests use
fixtures and do not produce FPGA performance numbers. The C tests require host
GCC. PCAP register-fixture tests check the real driver's sequencing/error paths;
physical configuration-engine operation remains unverified.

## Shared-family comparison

For a controlled three-way DPR study, build a single family and use its images
for all three firmware variants. `boot_firmware.tcl` accepts that family's
folder as its optional first argument; `host/dpr_client.py` accepts
`--images path/to/images.json`. Partial images from independent builds are not
interchangeable. Build tokens and SHA-256 checks reject accidental mixing.

Read [the complete experiment procedure](../README.md) for shared-family boot,
measurement boundaries, six-way comparison and pending physical validation.
The original LDACS SPEC-CHECK assumptions remain unresolved in every variant.

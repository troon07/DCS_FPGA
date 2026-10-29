# Hybrid benchmark transport

Build `build_firmware.py`, then boot `boot_firmware.tcl`. This image preserves the
original PS/PL algorithm partition while providing the common single-pass board
benchmark protocol. It uses the original parent bitstream and checked-in PS
preset, without editing the original firmware or replacing its built ELF.
See `../README.md` for the complete three-way procedure.

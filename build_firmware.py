# build_firmware.py
# Compiles uart_bridge.c into a bare-metal ARM ELF for the Zynq PS.
# Searches for arm-none-eabi-gcc in common Xilinx/Vitis/MinGW locations.
# Usage: python build_firmware.py
#   -> produces sw/uart_bridge.elf (loaded onto the board via XSDB)

import os
import sys
import subprocess
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SW_DIR     = os.path.join(SCRIPT_DIR, "sw")
SRC        = os.path.join(SW_DIR, "src", "uart_bridge.c")
LDSCRIPT   = os.path.join(SW_DIR, "ldacs_bridge.ld")
OUT_ELF    = os.path.join(SW_DIR, "uart_bridge.elf")

# Search paths for arm-none-eabi-gcc
SEARCH_DIRS = [
    r"C:\Xilinx\Vitis\2022.2\gnu\aarch32\nt\gcc-arm-none-eabi\bin",
    r"C:\Xilinx\Vitis\2021.2\gnu\aarch32\nt\gcc-arm-none-eabi\bin",
    r"C:\Xilinx\Vitis\2023.1\gnu\aarch32\nt\gcc-arm-none-eabi\bin",
    r"C:\Xilinx\Vitis\2023.2\gnu\aarch32\nt\gcc-arm-none-eabi\bin",
    r"C:\Program Files\GNU Arm Embedded Toolchain\10 2021.10\bin",
    r"C:\Program Files (x86)\GNU Tools ARM Embedded\9 2020-q2-update\bin",
]

def find_gcc():
    """Find arm-none-eabi-gcc in standard locations."""
    gcc = shutil.which("arm-none-eabi-gcc")
    if gcc:
        return gcc
    for d in SEARCH_DIRS:
        candidate = os.path.join(d, "arm-none-eabi-gcc.exe")
        if os.path.isfile(candidate):
            return candidate
    return None

def build():
    gcc = find_gcc()
    if gcc is None:
        print("[ERROR] arm-none-eabi-gcc not found.")
        print("  Install from: https://developer.arm.com/tools-and-software/open-source-software/developer-tools/gnu-toolchain/gnu-rm/downloads")
        print("  Or use Xilinx Vitis which bundles it.")
        print("")
        print("  After installing, re-run this script to build uart_bridge.elf")
        sys.exit(1)

    print(f"[BUILD] Using compiler: {gcc}")
    cmd = [
        gcc,
        "-mcpu=cortex-a9", "-mfpu=vfpv3", "-mfloat-abi=hard",
        "-O2", "-Wall", "-Iinclude",
        "-nostdlib", "-nostartfiles", "-ffreestanding",
        # The Xilinx Windows compiler wrapper mishandles absolute paths that
        # contain spaces.  Build from sw/ using relative paths instead.
        "-T", "ldacs_bridge.ld",
        "-o", "uart_bridge.elf",
        "src/uart_bridge.c", "src/helical.c", "src/derand.c",
        "-lgcc",
        "-e", "_start",
    ]
    print("[BUILD] Command:", " ".join(cmd))
    ret = subprocess.run(cmd, capture_output=True, text=True, cwd=SW_DIR)
    if ret.returncode != 0:
        print("[ERROR] Compilation failed:")
        print(ret.stderr)
        sys.exit(1)

    # Check ELF size
    size = os.path.getsize(OUT_ELF)
    print(f"[BUILD] SUCCESS: {OUT_ELF}  ({size} bytes)")
    return OUT_ELF


if __name__ == "__main__":
    build()

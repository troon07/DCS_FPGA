#!/usr/bin/env python3
"""Build the Cortex-A9 firmware; does not boot or program the board."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ARCH=0

def main():
    p=argparse.ArgumentParser();p.add_argument('--gcc',default=os.environ.get('ARM_GCC'));a=p.parse_args()
    gcc=a.gcc or shutil.which('arm-none-eabi-gcc')
    if not gcc:
        for version in ('2022.2','2023.2','2023.1','2021.2'):
            candidate=Path('C:/Xilinx/Vitis')/version/'gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe'
            if candidate.exists():gcc=str(candidate);break
    if not gcc:raise SystemExit('Install Vitis or Arm GNU toolchain, or pass --gcc /path/to/arm-none-eabi-gcc')
    sw=ROOT/'sw'
    sources=['src/uart_bridge.c','src/runtime.c']
    if ARCH in (0,2):sources+=['src/helical.c','src/derand.c']
    if ARCH==2:sources+=['src/receiver.c']
    cmd=[gcc,'-std=c11','-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard','-marm','-O2','-Wall','-Wextra',
         '-Wno-unused-function','-Wno-unused-variable','-Wno-unused-parameter','-Iinclude','-nostdlib','-nostartfiles',
         '-ffreestanding','-fno-builtin','-fno-stack-protector',f'-DARCH={ARCH}',
         '-T','ldacs_bridge.ld','-Wl,-Map,uart_bridge.map','-o','uart_bridge.elf',*sources,'-lgcc','-e','_start']
    subprocess.run(cmd,cwd=sw,check=True)
    metadata={'architecture':ARCH,'compiler':subprocess.check_output([gcc,'--version'],text=True).splitlines()[0],
              'flags':cmd[1:],'cache_policy':'I-cache and D-cache disabled for all variants',
              'elf_sha256':hashlib.sha256((sw/'uart_bridge.elf').read_bytes()).hexdigest(),
              'sources':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()
                         for f in sorted(sw.rglob('*')) if f.is_file() and f.suffix in ('.c','.h','.ld')}}
    (sw/'firmware_build.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print('Built',sw/'uart_bridge.elf')
if __name__=='__main__':main()

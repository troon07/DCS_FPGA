#!/usr/bin/env python3
"""Check all RM interfaces and static isolation logic in Icarus simulation."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
ROOT = Path(__file__).resolve().parents[1]
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--iverilog', default=shutil.which('iverilog'))
    p.add_argument('--vvp', default=shutil.which('vvp'))
    a = p.parse_args()
    if not a.iverilog or not a.vvp: p.error('Install Icarus or supply --iverilog and --vvp')
    out = ROOT / 'build/shell_test'; out.mkdir(parents=True, exist_ok=True)
    for rm in ('hybrid', 'full_pl', 'blank', 'anchor'):
        subprocess.run([a.iverilog, '-g2012', '-s', 'dpr_shell', '-o', str(out / (rm + '.vvp')),
                        str(ROOT / 'hw/static/dpr_shell.v'),
                        *map(str, (ROOT / 'hw/shared').glob('*.v')),
                        *map(str, (ROOT / 'hw/rm' / rm).glob('*.v'))], check=True)
    subprocess.run([a.iverilog, '-g2012', '-s', 'tb_shell', '-o', str(out / 'test.vvp'),
                    str(ROOT / 'tests/tb_shell.v'), str(ROOT / 'tests/mock_rp.v'),
                    str(ROOT / 'hw/static/dpr_shell.v')], check=True)
    result = subprocess.run([a.vvp, str(out / 'test.vvp')], capture_output=True, text=True, check=True)
    if 'SHELL TEST PASSED' not in result.stdout: raise RuntimeError(result.stdout + result.stderr)
    (out / 'validation.json').write_text(json.dumps({'board_measurement': False,
        'kind': 'static_shell_logic_simulation', 'rm_interfaces_compiled': 4,
        'passed': True, 'log': result.stdout}, indent=2) + '\n')
    print(result.stdout)
if __name__ == '__main__': main()

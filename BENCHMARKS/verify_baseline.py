#!/usr/bin/env python3
"""Verify original hybrid sources plus exact shared model/board-file copies."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    baseline = json.loads((ROOT / 'BENCHMARKS/baseline_manifest.json').read_text())['files']
    changed = [name for name, digest in baseline.items() if not (ROOT / name).exists() or sha(ROOT / name) != digest]
    if changed: raise SystemExit('Original hybrid files changed: ' + ', '.join(changed))
    shared = ['model/ldacs_ref.py', *[str(p.relative_to(ROOT)).replace('\\', '/')
                                    for p in (ROOT / 'board_details').rglob('*') if p.is_file()]]
    for variant in ('FULL_PL', 'FULL_PS'):
        for name in shared:
            if sha(ROOT / variant / name) != sha(ROOT / name):
                raise SystemExit(f'Shared source differs: {variant}/{name}')
    for name in ('bit2byte.v', 'block_deint.v', 'rs_dec.v', 'viterbi_dec.v'):
        if sha(ROOT / 'FULL_PL/hw/rtl' / name) != sha(ROOT / 'hw/rtl' / name):
            raise SystemExit('Copied baseline RTL changed: ' + name)
    print(f'PASS: {len(baseline)} original hybrid files unchanged; reference models, board files and reused PL cores match')
if __name__ == '__main__': main()

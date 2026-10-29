#!/usr/bin/env python3
"""Verify all pre-existing source files and common DPR shell/module copies."""
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    manifest = json.loads((ROOT / 'DPR/preserved_sources.json').read_text())
    for name, expected in manifest.items():
        if digest(ROOT / name) != expected: raise SystemExit('Pre-existing file changed: ' + name)
    common = ROOT / 'DPR/FULL_PL'
    for variant in ('HYBRID', 'FULL_PS'):
        other = ROOT / 'DPR' / variant
        for source in (common / 'hw').rglob('*.v'):
            relative = source.relative_to(common)
            if relative.parts[1] == 'tb': continue  # Different data boundaries per partition.
            if digest(source) != digest(other / relative): raise SystemExit('Common DPR hardware differs: ' + str(relative))
    for variant in ('HYBRID', 'FULL_PL', 'FULL_PS'):
        if digest(ROOT / 'DPR' / variant / 'model/ldacs_ref.py') != digest(ROOT / 'model/ldacs_ref.py'):
            raise SystemExit('Reference model differs: ' + variant)
    print(f'PASS: {len(manifest)} pre-existing source files preserved; DPR shell/modules and reference models match')
if __name__ == '__main__': main()

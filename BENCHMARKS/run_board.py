#!/usr/bin/env python3
"""Collect comparable one-pass measurements from firmware already booted on board."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('board_client', ROOT / 'FULL_PS/host/board_client.py')
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--variant', required=True, choices=['HYBRID', 'FULL_PL', 'FULL_PS'])
    p.add_argument('--port', default='COM5')
    p.add_argument('--mode', default='all', choices=['all', *client.L.MODES])
    p.add_argument('--iterations', type=int, default=20)
    p.add_argument('--warmups', type=int, default=2)
    p.add_argument('--batches', type=int, default=5)
    p.add_argument('--seed', type=int, default=91)
    p.add_argument('--timeout', type=float, default=300)
    p.add_argument('--board-label', default='EDGE Z7-10 / XC7Z010CLG400-1')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    arch = {'HYBRID': 0, 'FULL_PL': 1, 'FULL_PS': 2}[a.variant]
    source = ROOT / ('BENCHMARKS/hybrid' if arch == 0 else a.variant)
    board = client.Board(a.port, a.timeout)
    try:
        modes = list(client.L.MODES) if a.mode == 'all' else [a.mode]
        result = client.collect(board, modes, a.iterations, a.warmups, a.batches, a.seed, arch, source)
        result['board_label'] = a.board_label
        if arch == 0:
            original = client.provenance(ROOT)
            for key in ('reference_model', 'bitstream', 'routed_build'): result['artifacts'][key] = original[key]
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2) + '\n')
        for row in result['results']:
            reps = sum(s['iterations'] for s in row['samples'])
            micros = sum(s['decoder_ticks_sum'] / s['global_timer_hz'] * 1e6 for s in row['samples'])
            print(f"{a.variant} {row['mode']}: {micros / reps:.3f} us/frame, {reps} measured frames")
        print('Saved', a.output)
        if not result['valid']: raise SystemExit(2)
    finally: board.close()

if __name__ == '__main__': main()

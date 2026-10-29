#!/usr/bin/env python3
"""Simulate actual FULL_PL RTL against all Python reference stage buffers."""
import argparse
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model import ldacs_ref as L

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--iverilog', default=shutil.which('iverilog'))
    p.add_argument('--vvp', default=shutil.which('vvp'))
    p.add_argument('--quick', action='store_true')
    args = p.parse_args()
    if not args.iverilog or not args.vvp: p.error('Install Icarus Verilog or pass --iverilog and --vvp')
    cases = [(m, 0.0, 0) for m in (['qpsk_1_2'] if args.quick else L.MODES)]
    cases += [('qpsk_1_2', 0.02, 0)]
    if not args.quick: cases += [('qpsk_3_4', 0.01, 0), ('qpsk_3_4', 0.04, 0)]
    cases += [('qpsk_1_2', 0.01, tap) for tap in (1, 2)]
    results = []
    for mode, ber, tap in cases:
        layout = L.frame_layout(mode)
        payload = bytes((i * 37 + len(mode)) & 255 for i in range(layout['payload_bytes']))
        tx = L.add_errors(L.encode_frame(payload, layout)['tx'], random.Random(27), ber=ber)
        dec = L.decode_frame(tx, layout)
        expected = {0: dec['hw_out'], 1: dec['viterbi_bytes'], 2: dec['block_deinterleaved'],
                    3: bytes(dec['vit_in']), 4: dec['hw_out']}[tap]
        work = ROOT / 'build' / f'sim_{mode}_{ber}_tap{tap}'
        work.mkdir(parents=True, exist_ok=True)
        def mem(name, data): (work / name).write_text(''.join(f'{b:02x}\n' for b in data))
        mem('vit_in.mem', bytes(L.helical_deinterleave(tx)))  # FULL_PL consumes original interleaved TX bits.
        mem('hw_expected.mem', expected)
        config = {'CFG_RATE': L.RATE_CODE[layout['rate']], 'CFG_N_STEPS': layout['n_steps'],
                  'CFG_NUM_CW': layout['num_cw'], 'CFG_RS_N': layout['rs_n'], 'CFG_TRACE': tap,
                  'N_IN': len(tx), 'N_OUT': len(expected),
                  'EXP_CORR': dec['n_corr'] if tap in (0, 4) else 0,
                  'EXP_FAIL': dec['n_fail'] if tap in (0, 4) else 0}
        (work / 'tb_cfg.vh').write_text(''.join(f'localparam {k}={v};\n' for k, v in config.items()))
        cmd = [args.iverilog, '-g2012', '-s', 'tb_decoder_top', '-I', '.', '-o', 'sim.vvp',
               str(ROOT / 'hw/tb/tb_decoder_top.v'), str(ROOT / 'hw/static/dpr_shell.v'), *map(str, sorted((ROOT / 'hw/shared').glob('*.v'))), *map(str, sorted((ROOT / 'hw/rm/hybrid').glob('*.v')))]
        built = subprocess.run(cmd, cwd=work, text=True, capture_output=True, timeout=120)
        (work / 'compile.log').write_text(built.stdout + built.stderr)
        if built.returncode: raise RuntimeError(built.stderr)
        sim = subprocess.run([args.vvp, 'sim.vvp'], cwd=work, text=True, capture_output=True, timeout=240)
        (work / 'sim.log').write_text(sim.stdout + sim.stderr)
        if sim.returncode or 'TEST PASSED' not in sim.stdout: raise RuntimeError(sim.stdout + sim.stderr)
        print(f'PASS RTL {mode} BER={ber} trace={tap} ({len(expected)} output bytes)', flush=True)
        results.append({'mode': mode, 'ber': ber, 'tap': tap, 'match': True})
    report = {'kind': 'rtl_functional_simulation', 'board_measurement': False, 'cases': results}
    (ROOT / ('build/rtl_validation_quick.json' if args.quick else 'build/rtl_validation.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(f'{len(results)} DPR HYBRID simulations passed with random input gaps and backpressure')

if __name__ == '__main__': main()

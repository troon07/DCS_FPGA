#!/usr/bin/env python3
"""Build and exercise the actual PS C algorithms on the host against Python.
Host timings are NOT board benchmark results. Requires gcc; no FPGA required.
"""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model import ldacs_ref as L

class Config(C.Structure):
    _fields_ = [(n, C.c_uint) for n in ('rate', 'coded', 'steps', 'cw', 'n', 'payload')]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gcc', default='gcc')
    args = parser.parse_args()
    build = ROOT / 'build' / 'host_validation'
    build.mkdir(parents=True, exist_ok=True)
    dll = build / ('receiver.dll' if os.name == 'nt' else 'receiver.so')
    sources = [ROOT / 'sw/src' / n for n in ('receiver.c', 'helical.c', 'derand.c')]
    subprocess.run([args.gcc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-shared', *([] if os.name == 'nt' else ['-fPIC']),
                    '-I' + str(ROOT / 'sw/include'), *map(str, sources), '-o', str(dll)], check=True)
    lib = C.CDLL(str(dll))
    u8p = C.POINTER(C.c_uint8)
    lib.rx_viterbi.argtypes = [u8p, u8p, C.POINTER(Config)]
    lib.rx_block_deinterleave.argtypes = [u8p, u8p, C.POINTER(Config)]
    lib.rx_rs_word.argtypes = [u8p, u8p, C.c_uint, C.POINTER(C.c_uint)]
    lib.helical_deinterleave.argtypes = [u8p, u8p, C.c_size_t]
    lib.derandomize.argtypes = [u8p, u8p, C.c_size_t]
    lib.rx_init()
    def array(values): return (C.c_uint8 * len(values))(*values)
    records = []
    for mode in L.MODES:
        layout = L.frame_layout(mode)
        payload = bytes((i * 37 + len(mode)) & 255 for i in range(layout['payload_bytes']))
        encoded = L.encode_frame(payload, layout)
        cfg = Config(L.RATE_CODE[layout['rate']], layout['coded_bits'], layout['n_steps'],
                     layout['num_cw'], layout['rs_n'], layout['payload_bytes'])
        for ber in (0.0, 0.01, 0.035):
            bits = L.add_errors(encoded['tx'], random.Random(91), ber=ber)
            reference = L.decode_frame(bits, layout)
            helical = array([0] * len(bits))
            nrs = cfg.cw * cfg.n
            vit, block = array([0] * nrs), array([0] * nrs)
            rs, final = array([0] * cfg.payload), array([0] * cfg.payload)
            lib.helical_deinterleave(array(bits), helical, len(bits))
            assert bytes(helical) == bytes(reference['vit_in']), (mode, ber, 'helical')
            assert lib.rx_viterbi(helical, vit, C.byref(cfg)) == 0
            assert bytes(vit) == reference['viterbi_bytes'], (mode, ber, 'viterbi')
            lib.rx_block_deinterleave(vit, block, C.byref(cfg))
            assert bytes(block) == reference['block_deinterleaved'], (mode, ber, 'block')
            corrected = failed = 0
            for cw in range(cfg.cw):
                count = C.c_uint()
                status = lib.rx_rs_word(C.cast(C.byref(block, cw * cfg.n), u8p),
                                        C.cast(C.byref(rs, cw * (cfg.n - 10)), u8p), cfg.n, C.byref(count))
                assert status >= 0
                corrected += count.value
                failed += status != 0
            assert (bytes(rs), corrected, failed) == (reference['hw_out'], reference['n_corr'], reference['n_fail'])
            lib.derandomize(rs, final, cfg.payload)
            assert bytes(final) == reference['payload'], (mode, ber, 'derandomizer')
            if ber == 0: assert bytes(final) == payload
            records.append({'mode': mode, 'ber': ber, 'stages_match': True,
                            'rs_corrected': corrected, 'rs_failed': failed})
            print(f'PASS C/Python all five stages: {mode} BER={ber} corrected={corrected} failed={failed}')
    # Direct RS tests ensure the correction branches are exercised independently
    # of the convolutional code correcting channel noise first.
    for errors in range(9):
        rng = random.Random(32 + errors)
        message = bytes(rng.randrange(256) for _ in range(91))
        word = bytearray(L.rs_encode(message))
        for pos in rng.sample(range(101), errors): word[pos] ^= rng.randrange(1, 256)
        expected, ncorrected, ok = L.rs_decode(word)
        output, count = array([0] * 91), C.c_uint()
        status = lib.rx_rs_word(array(word), output, 101, C.byref(count))
        assert (bytes(output), count.value, status == 0) == (expected, ncorrected, ok)
        if errors <= 5: assert bytes(output) == message and status == 0
    print('PASS direct RS 0..8 symbol-error cases, including correction and failure paths')
    report = {'kind': 'host_functional_validation', 'board_measurement': False,
              'frame_cases': records, 'direct_rs_cases': 9}
    (build / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'{len(records)} frame cases and 9 direct RS cases passed')

if __name__ == '__main__': main()

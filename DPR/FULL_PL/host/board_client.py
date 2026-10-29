#!/usr/bin/env python3
"""Real-board receiver client. Never substitutes a model result for board data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import struct
import sys
import time
import zlib
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model import ldacs_ref as L

ARCHITECTURE = 1
ARCH_NAMES = {0: 'HYBRID', 1: 'FULL_PL', 2: 'FULL_PS'}
STAGES = ['helical', 'viterbi', 'block_deinterleaver', 'reed_solomon', 'derandomizer']
RESPONSE = struct.Struct('<4sBBHHHIIIII9Q')

def digest(data): return hashlib.sha256(bytes(data)).hexdigest()

def prepare(mode, seed=91, text=None, ber=0.0):
    layout = L.frame_layout(mode)
    rng = random.Random(seed)
    payload = bytes(rng.randrange(256) for _ in range(layout['payload_bytes']))
    if text is not None:
        raw = text.encode('utf-8')
        if len(raw) > len(payload): raise ValueError('Message exceeds this mode\'s frame payload capacity')
        payload = raw.ljust(len(payload), b'\0')
    encoded = L.encode_frame(payload, layout)
    tx = bytes(L.add_errors(encoded['tx'], random.Random(seed + 1), ber=ber))
    return layout, payload, tx

def header(magic, layout):
    return magic + struct.pack('<BHHHHB', L.RATE_CODE[layout['rate']], layout['coded_bits'],
                               layout['payload_bytes'], layout['n_steps'], layout['num_cw'], layout['rs_n'])

class Board:
    def __init__(self, port='COM5', timeout=300, serial_port=None):
        self.timeout = timeout
        if serial_port is None:
            import serial
            serial_port = serial.Serial(port, 115200, timeout=0.2, write_timeout=30)
        self.serial = serial_port
        self.port = port
    def close(self): self.serial.close()
    def read(self, n):
        output = bytearray()
        deadline = time.monotonic() + self.timeout
        while len(output) < n:
            chunk = self.serial.read(n - len(output))
            output.extend(chunk)
            if time.monotonic() > deadline: raise TimeoutError(f'Board short read: {len(output)}/{n} bytes')
        return bytes(output)
    def send(self, packet):
        self.serial.reset_input_buffer()
        written = self.serial.write(packet)
        if written != len(packet): raise IOError('Incomplete UART write')
        self.serial.flush()
    def magic(self, expected):
        value = self.read(4)
        if value == b'\xff' * 4: raise RuntimeError('Board rejected configuration or reported DMA/version error')
        if value != expected: raise RuntimeError(f'Wrong firmware/protocol: received {value!r}, expected {expected!r}')

    def benchmark(self, layout, payload, tx, iterations=20, warmups=2, architecture=ARCHITECTURE):
        if not 1 <= iterations <= 1000 or not 0 <= warmups <= 100: raise ValueError('Invalid repetitions/warmups')
        start = time.perf_counter_ns()
        self.send(header(b'LDB1', layout) + struct.pack('<HHI', iterations, warmups, zlib.crc32(payload)) + tx)
        self.magic(b'DDBR')
        raw = b'DDBR' + self.read(RESPONSE.size - 4)
        (magic, arch, rate, reps, length, warm, gt_hz, pl_hz, corrected, failed, bad, *counts) = RESPONSE.unpack(raw)
        expected = (architecture, L.RATE_CODE[layout['rate']], iterations, len(payload), warmups)
        if (arch, rate, reps, length, warm) != expected: raise RuntimeError('Firmware architecture/configuration mismatch')
        if not gt_hz or (arch != 2 and not pl_hz): raise RuntimeError('Board returned invalid clock configuration')
        stage_counts, total, minimum, maximum, pipeline = counts[:5], *counts[5:]
        if not total or not minimum or not all(stage_counts) or not minimum <= total / reps <= maximum:
            raise RuntimeError('Invalid board timing counters')
        output = self.read(length)
        elapsed = (time.perf_counter_ns() - start) / 1e6
        frequencies = [pl_hz if arch == 1 or (arch == 0 and 1 <= i <= 3) else gt_hz for i in range(5)]
        stages = {name: {'ticks_sum': ticks, 'clock_hz': hz, 'mean_us': ticks * 1e6 / hz / reps}
                  for name, ticks, hz in zip(STAGES, stage_counts, frequencies)}
        return {
            'measurement': 'real_board_uart_response', 'architecture': ARCH_NAMES[arch],
            'iterations': reps, 'warmups': warm, 'global_timer_hz': gt_hz, 'pl_clock_hz': pl_hz,
            'raw_response_header_hex': raw.hex(), 'stage_measurements': stages,
            'decoder_ticks_sum': total, 'decoder_ticks_min': minimum, 'decoder_ticks_max': maximum,
            'decoder_mean_us': total * 1e6 / gt_hz / reps,
            'decoder_min_us': minimum * 1e6 / gt_hz, 'decoder_max_us': maximum * 1e6 / gt_hz,
            'decoder_payload_mbps': len(payload) * 8 * gt_hz * reps / total / 1e6,
            'pl_pipeline_ticks_sum': pipeline,
            'pl_pipeline_mean_us': pipeline * 1e6 / pl_hz / reps if arch != 2 else None,
            'uart_batch_wall_ms': elapsed, 'rs_corrections': corrected, 'rs_failures': failed,
            'crc_failed_frames': bad, 'last_output_sha256': digest(output),
            'last_output_matches': output == payload,
            'valid': output == payload and failed == 0 and bad == 0,
        }

    def trace(self, layout, payload, tx, architecture=ARCHITECTURE):
        start = time.perf_counter_ns()
        self.send(header(b'LDAC', layout) + tx)
        self.magic(b'DTR4')
        arch = self.read(1)[0]
        if arch != architecture: raise RuntimeError('Wrong architecture firmware is running')
        nrs = layout['num_cw'] * layout['rs_n']
        meta = struct.unpack('<7H8I', self.read(46))
        lengths, corrected, failed = meta[:5], meta[5], meta[6]
        cycles, hz = meta[7:14], meta[14]
        if lengths != (len(tx), nrs, nrs, len(payload), len(payload)) or not hz:
            raise RuntimeError('Invalid trace lengths/clock')
        buffers = [self.read(n) for n in lengths]
        model = L.decode_frame(tx, layout)
        expected = [bytes(model['vit_in']), model['viterbi_bytes'], model['block_deinterleaved'],
                    model['hw_out'], model['payload']]
        return {'measurement': 'real_board_stage_trace', 'architecture': ARCH_NAMES[arch],
                'global_timer_hz': hz, 'stage_ticks_gt_equivalent': list(cycles[:4]) + [cycles[5]],
                'decoder_ticks_gt': cycles[6], 'pipeline_ticks_gt_equivalent': cycles[4],
                'uart_trace_wall_ms': (time.perf_counter_ns() - start) / 1e6,
                'rs_corrections': corrected, 'rs_failures': failed,
                'stages': {name: {'matches_model': got == exp, 'length': len(got), 'sha256': digest(got),
                                  'output_hex': got.hex()}
                           for name, got, exp in zip(STAGES, buffers, expected)},
                'payload_matches_input': buffers[-1] == payload,
                'recovered_text': buffers[-1].rstrip(b'\0').decode('utf-8', errors='replace')}

def provenance(root=ROOT, report_dir=None):
    files = {'firmware': root / 'sw/uart_bridge.elf',
             'bitstream': root / 'hw/vivado/build/ldacs_zed/ldacs_zed.runs/impl_1/system_wrapper.bit',
             'reference_model': root / 'model/ldacs_ref.py'}
    result = {k: {'path': str(p), 'sha256': digest(p.read_bytes()) if p.exists() else None} for k, p in files.items()}
    metadata = root / 'sw/firmware_build.json'
    result['firmware_build'] = json.loads(metadata.read_text()) if metadata.exists() else None
    report_dir = Path(report_dir) if report_dir is not None else root / 'hw/vivado/build/dfx'
    metrics = {}
    for name in ('utilization.rpt', 'timing.rpt', 'power_estimate.rpt'):
        module={0:'hybrid',1:'full_pl',2:'blank'}[ARCHITECTURE]
        path = report_dir / (module+'_'+name)
        metrics[name] = {'sha256': digest(path.read_bytes()) if path.exists() else None}
        if not path.exists(): continue
        text = path.read_text(errors='replace')
        if name == 'utilization.rpt':
            for key, label in (('lut', 'Slice LUTs'), ('ff', 'Slice Registers'),
                               ('bram', 'Block RAM Tile'), ('dsp', 'DSPs')):
                match = re.search(r'\|\s*' + label + r'\s*\|\s*([0-9.]+)', text)
                metrics[key] = float(match.group(1)) if match else None
        if name == 'timing.rpt':
            match = re.search(r'WNS\(ns\).*?\n[^\n]*\n\s*([-+0-9.]+)', text, re.S)
            metrics['wns_ns'] = float(match.group(1)) if match else None
    result['routed_build'] = metrics
    return result

def collect(board, modes, iterations=20, warmups=2, batches=5, seed=91, architecture=ARCHITECTURE, root=ROOT):
    if batches < 1: raise ValueError('At least one batch required')
    records = []
    for mode in modes:
        layout, payload, tx = prepare(mode, seed)
        samples = [board.benchmark(layout, payload, tx, iterations, warmups, architecture) for _ in range(batches)]
        records.append({'mode': mode, 'layout': layout, 'payload_sha256': digest(payload),
                        'encoded_frame_sha256': digest(tx), 'samples': samples})
    return {'schema': 'ldacs_partition_benchmark_v1', 'recorded_utc': datetime.now(timezone.utc).isoformat(),
            'architecture': ARCH_NAMES[architecture], 'port': board.port, 'baud': 115200,
            'seed': seed, 'iterations_per_batch': iterations, 'warmups_per_batch': warmups, 'batches': batches,
            'cache_policy': 'I-cache and D-cache disabled; single Cortex-A9 core; warmups explicitly counted',
            'clock_source': 'Live Zynq SLCR divisors with nominal 33333333 Hz PS reference oscillator',
            'decoder_scope': 'one complete five-stage decode; includes DMA/control for PL; excludes UART, CRC and output copy',
            'transport_scope': 'UART batch wall time includes input/output, warmups, repetitions and CRC checks',
            'limitations': ['SPEC-CHECK constants are shared; independent LDACS conformance is unverified',
                            'No board power measurement; Vivado power reports are estimates',
                            'No RF, synchronization, channel estimation or demapping is included',
                            'Payload checks use per-frame CRC32 and exact final-frame byte comparison'],
            'artifacts': provenance(root), 'results': records,
            'valid': all(s['valid'] for r in records for s in r['samples'])}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['benchmark', 'trace'])
    parser.add_argument('--port', default='COM5')
    parser.add_argument('--mode', choices=['all', *L.MODES], default='all')
    parser.add_argument('--iterations', type=int, default=20)
    parser.add_argument('--warmups', type=int, default=2)
    parser.add_argument('--batches', type=int, default=5)
    parser.add_argument('--seed', type=int, default=91)
    parser.add_argument('--message', default='LDACS PARTITION RESEARCH')
    parser.add_argument('--timeout', type=float, default=300)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    board = Board(args.port, args.timeout)
    try:
        if args.command == 'benchmark':
            modes = list(L.MODES) if args.mode == 'all' else [args.mode]
            result = collect(board, modes, args.iterations, args.warmups, args.batches, args.seed)
        else:
            if args.mode == 'all': parser.error('Select one --mode for a trace')
            layout, payload, tx = prepare(args.mode, args.seed, args.message)
            result = board.trace(layout, payload, tx)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        print('Saved actual board response to', args.output)
        if args.command == 'benchmark' and not result['valid']: raise SystemExit(2)
    finally: board.close()

if __name__ == '__main__':
    raise SystemExit('Use host/dpr_client.py for DPR captures with switch and image provenance.')

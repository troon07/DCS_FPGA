#!/usr/bin/env python3
"""Real ARM-controlled PCAP switches; image staging is outside switch timing."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import time
import zlib
import board_client as base

ROOT = Path(__file__).resolve().parents[1]
ARCH = base.ARCHITECTURE
NAME = {0: 'DPR_HYBRID', 1: 'DPR_FULL_PL', 2: 'DPR_FULL_PS'}[ARCH]
TARGET = {0: 'hybrid', 1: 'full_pl', 2: 'blank'}[ARCH]

def family(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('schema') != 'ldacs_dpr_image_family_v1' or not value.get('pr_verify_passed'):
        raise ValueError('Unverified or unsupported image family')
    marker=path.parent/'routed_manifest.json'
    if marker.exists():
        current=json.loads(marker.read_text(encoding='utf-8'))
        if not current.get('pr_verify_passed') or current.get('build_token')!=value['build_token']:
            raise ValueError('Image package is stale or a later implementation failed')
    if value['part'] != 'xc7z010clg400-1': raise ValueError('Wrong FPGA part')
    if set(value['modules']) != {'hybrid', 'full_pl', 'blank', 'anchor'}: raise ValueError('Incomplete family')
    for name, module in value['modules'].items():
        if module['id']!={'hybrid':0,'full_pl':1,'blank':2,'anchor':3}[name]:
            raise ValueError('Incorrect module identity mapping')
        path_ = (path.parent / module['partial_file']).resolve()
        if path_.parent != path.parent.resolve(): raise ValueError('Partial image must be beside its manifest')
        full = path.parent / module['full_file']
        if full.resolve().parent != path.parent.resolve() or hashlib.sha256(full.read_bytes()).hexdigest() != module['full_sha256']:
            raise ValueError('Full boot image hash/path mismatch: ' + name)
        data = path_.read_bytes()
        if hashlib.sha256(data).hexdigest() != module['partial_sha256'] or len(data) != module['partial_bytes']:
            raise ValueError('Partial image hash/size mismatch: ' + name)
    return value

class DPRBoard(base.Board):
    def magic(self, expected):
        value = self.read(4)
        if value == b'DPRE': raise RuntimeError(f'DPR firmware error {struct.unpack("<I", self.read(4))[0]}; inspect status; failed loads remain isolated')
        if value == b'\xff' * 4: raise RuntimeError('Decoder/DMA rejected request or wrong module is loaded')
        if value != expected: raise RuntimeError(f'Wrong DPR firmware response: {value!r}')
    def status(self):
        self.send(b'DPS1'); self.magic(b'DPSR')
        fields = struct.unpack('<8I', self.read(32))
        names = ('firmware_arch', 'shell_magic', 'build_token', 'module_id', 'isolation_reset', 'generation', 'global_timer_hz', 'last_error')
        result = dict(zip(names, fields))
        if result['firmware_arch'] != ARCH or result['shell_magic'] != 0x44505231:
            raise RuntimeError('Wrong DPR shell or ARM architecture')
        return result
    def upload(self, manifest, module, directory):
        entry = manifest['modules'][module]
        data = (directory / entry['partial_file']).read_bytes()
        state = self.status()
        if state['build_token'] != manifest['build_token']: raise RuntimeError('Image family does not match running static shell')
        start = time.perf_counter()
        crc = zlib.crc32(data)
        self.send(b'DPU1' + struct.pack('<BIII', entry['id'], manifest['build_token'], len(data), crc))
        self.magic(b'RDY1')
        # Small writes bound serial-library timeout; the board caches in DDR.
        for i in range(0, len(data), 4096):
            part = data[i:i+4096]
            if self.serial.write(part) != len(part): raise IOError('Short partial-image upload')
        self.serial.flush(); self.magic(b'DPUA')
        if struct.unpack('<III', self.read(12)) != (entry['id'], len(data), crc): raise RuntimeError('Upload acknowledgement mismatch')
        return {'module': module, 'partial_sha256': entry['partial_sha256'], 'bytes': len(data),
                'host_upload_seconds': time.perf_counter() - start, 'included_in_switch_latency': False}
    def switch(self, manifest, module):
        before = self.status()
        if before['build_token'] != manifest['build_token']: raise RuntimeError('Wrong static image family')
        start = time.perf_counter_ns()
        target = manifest['modules'][module]['id']
        self.send(b'DPR1' + bytes([target])); self.magic(b'DPRR')
        values = struct.unpack('<7I7Q', self.read(84))
        old, new, token, generation, hz, size, flags, isolate, load, restart, total, downtime, precheck, service_total = values
        if (old, new, token, generation, size) != (before['module_id'], target, manifest['build_token'], before['generation'] + 1, manifest['modules'][module]['partial_bytes']):
            raise RuntimeError('Switch identity/generation/size mismatch')
        if not hz or not total or load > total or downtime > total or service_total < total: raise RuntimeError('Invalid switch counters')
        after = self.status()
        if after['module_id'] != target or after['isolation_reset'] or after['last_error']:
            raise RuntimeError('Replacement did not restart cleanly')
        return {'measurement': 'real_board_pcap_partial_switch', 'module': module,
                'from_id': old, 'to_id': new, 'build_token': token, 'generation': generation,
                'global_timer_hz': hz, 'partial_bytes': size, 'devcfg_interrupts': flags,
                'ticks': dict(zip(('isolation', 'pcap', 'restart', 'total', 'unavailable', 'precheck', 'service_total'), values[7:])),
                'microseconds': {k: v * 1e6 / hz for k, v in zip(('isolation', 'pcap', 'restart', 'total', 'unavailable', 'precheck', 'service_total'), values[7:])},
                'host_control_wall_ms': (time.perf_counter_ns() - start) / 1e6}

def collect(board, image_path, modes, iterations, warmups, batches, switches, seed):
    manifest = family(image_path)
    state = board.status()
    if state['build_token'] != manifest['build_token']: raise RuntimeError('Boot an image from this exact build')
    alternate = 'anchor' if ARCH == 2 else 'blank'
    uploads = [board.upload(manifest, name, image_path.parent) for name in (alternate, TARGET)]
    transitions = []
    for _ in range(switches):
        transitions.append(board.switch(manifest, alternate))
        transitions.append(board.switch(manifest, TARGET))
        # Check complete recovered payload after EVERY round trip before continuing.
        lay, payload, tx = base.prepare('qpsk_1_2', seed)
        check = board.benchmark(lay, payload, tx, 1, 0, ARCH)
        if not check['valid']: raise RuntimeError('Decode failed after a partial switch')
        transitions[-1]['post_switch_decode'] = check
    capture = base.collect(board, modes, iterations, warmups, batches, seed, ARCH, ROOT)
    capture.update(schema='ldacs_dpr_benchmark_v1', architecture=NAME,
                   image_family=manifest, initial_status=state, image_uploads=uploads, switches=transitions,
                   recorded_utc=datetime.now(timezone.utc).isoformat(),
                   reconfiguration_scope='idle -> isolate -> cached-DDR PCAP load -> reset/restart/identity; total excludes image upload/CRC precheck; service_total includes CRC precheck')
    entry = manifest['modules'][TARGET]
    capture['artifacts']['routed_build'] = base.provenance(ROOT, image_path.parent)['routed_build']
    capture['artifacts']['bitstream'] = {'path': str(image_path.parent / entry['full_file']), 'sha256': entry['full_sha256']}
    for row in capture['results']:
        for sample in row['samples']: sample['execution_platform'] = NAME
    return capture

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--images', type=Path, default=ROOT / 'hw/vivado/build/dfx/images.json')
    p.add_argument('--port', default='COM5'); p.add_argument('--mode', choices=['all', *base.L.MODES], default='all')
    p.add_argument('--iterations', type=int, default=20); p.add_argument('--warmups', type=int, default=2)
    p.add_argument('--batches', type=int, default=5); p.add_argument('--switches', type=int, default=3)
    p.add_argument('--board-label', default='EDGE Z7-10 / XC7Z010CLG400-1')
    p.add_argument('--seed', type=int, default=91); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not 1 <= a.switches <= 100: p.error('Use 1..100 switch round trips')
    # Validate local image family before opening a serial port.
    family(a.images)
    board = DPRBoard(a.port, timeout=600)
    try:
        result = collect(board, a.images, list(base.L.MODES) if a.mode == 'all' else [a.mode],
                         a.iterations, a.warmups, a.batches, a.switches, a.seed)
        result['board_label'] = a.board_label
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print('Saved physical-board DPR capture:', a.output)
        if not result['valid']: raise SystemExit(2)
    finally: board.close()
if __name__ == '__main__': main()

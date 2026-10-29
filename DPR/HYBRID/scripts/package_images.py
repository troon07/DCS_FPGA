#!/usr/bin/env python3
"""Package only a successfully routed/pr_verify-checked DFX image family."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = {'hybrid': 0, 'full_pl': 1, 'blank': 2, 'anchor': 3}
def sha(data): return hashlib.sha256(data).hexdigest()
def pcap_words(data):
    if not data or len(data) % 4: raise ValueError('Raw Vivado .bin must contain complete 32-bit words')
    big = data.find(bytes.fromhex('aa995566'), 0, 1024)
    little = data.find(bytes.fromhex('665599aa'), 0, 1024)
    if big >= 0 and big % 4 == 0:
        offset, order = big, 'big'
        result = b''.join(data[i:i+4][::-1] for i in range(0, len(data), 4))
    elif little >= 0 and little % 4 == 0:
        offset, order, result = little, 'little', data
    else: raise ValueError('No aligned configuration sync word; use Vivado raw .bin, not a .bit header')
    allowed = {0xffffffff, 0, 0x000000bb, 0x11220044}
    if any(int.from_bytes(data[i:i+4], order) not in allowed for i in range(0, offset, 4)):
        raise ValueError('Unexpected preamble: container .bit headers must not be sent to PCAP')
    return result
def main():
    out = ROOT / 'hw/vivado/build/dfx'
    marker = json.loads((out / 'routed_manifest.json').read_text())
    if marker.get('schema') != 'ldacs_dfx_routed_v1' or not marker.get('pr_verify_passed'):
        raise RuntimeError('No completed, verified DFX implementation')
    static = (out / 'static_locked.dcp').read_bytes()
    family = {'schema': 'ldacs_dpr_image_family_v1', 'build_token': marker['build_token'],
              'part': marker['part'], 'rp_cell': marker['rp_cell'], 'pr_verify_passed': True,
              'static_checkpoint_sha256': sha(static), 'modules': {}}
    for module, ident in MODULES.items():
        partial = out / f'{module}_partial.bin'
        data = pcap_words(partial.read_bytes())
        if len(data) > 8 * 1024 * 1024: raise ValueError('Image exceeds one firmware cache slot')
        packaged = out / f'{module}.pcap.bin'
        packaged.write_bytes(data)
        full = out / f'{module}.bit'
        family['modules'][module] = {'id': ident, 'partial_file': packaged.name,
            'partial_bytes': len(data), 'partial_sha256': sha(data),
            'full_file': full.name, 'full_sha256': sha(full.read_bytes()),
            'routed_checkpoint_sha256': sha((out / f'{module}_routed.dcp').read_bytes())}
    (out / 'images.json').write_text(json.dumps(family, indent=2) + '\n', encoding='utf-8')
    print('Packaged same-static image family:', out / 'images.json')
if __name__ == '__main__': main()

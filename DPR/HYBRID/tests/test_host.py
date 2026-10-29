"""Host-side DPR protocol fixtures. No simulated value is a board benchmark."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'host'))
import dpr_client as client
spec = importlib.util.spec_from_file_location('package_images', ROOT / 'scripts/package_images.py')
package = importlib.util.module_from_spec(spec); spec.loader.exec_module(package)

class Serial:
    def __init__(self, response): self.data = bytearray(response); self.writes = []
    def read(self, n):
        n = min(n, 3); data = bytes(self.data[:n]); del self.data[:n]; return data
    def write(self, data): self.writes.append(data); return len(data)
    def reset_input_buffer(self): pass
    def flush(self): pass
    def close(self): pass

class Tests(unittest.TestCase):
    def status(self, ident=2, generation=5, token=77):
        return b'DPSR' + struct.pack('<8I', client.ARCH, 0x44505231, token, ident, 0, generation, 1000, 0)
    def test_big_endian_pcap_conversion(self):
        data = bytes.fromhex('ffffffff000000bb11220044aa99556620000000')
        self.assertEqual(package.pcap_words(data)[12:16], bytes.fromhex('665599aa'))
    def test_little_endian_pcap_preserved(self):
        data = bytes.fromhex('ffffffff665599aa00000020')
        self.assertEqual(package.pcap_words(data), data)
    def test_container_header_rejected(self):
        with self.assertRaises(ValueError): package.pcap_words(b'HEAD' + bytes.fromhex('aa995566'))
    def test_unaligned_and_missing_sync_rejected(self):
        for data in (b'x', b'\0' * 16, b'x' + bytes.fromhex('aa995566') + b'xxx'):
            with self.assertRaises(ValueError): package.pcap_words(data)
    def test_switch_counter_decode(self):
        target = client.ARCH
        module = client.TARGET
        reply = b'DPRR' + struct.pack('<7I7Q', 2, target, 77, 6, 1000, 16, 0x3000, 10, 100, 20, 140, 130, 50, 200)
        serial = Serial(self.status() + reply + self.status(target, 6))
        board = client.DPRBoard(serial_port=serial)
        result = board.switch({'build_token': 77, 'modules': {module: {'id': target, 'partial_bytes': 16}}}, module)
        self.assertEqual(result['ticks']['pcap'], 100)
        self.assertEqual(result['microseconds']['total'], 140000)
        self.assertIn(b'DPR1' + bytes([target]), serial.writes)
    def test_wrong_shell_rejected_before_switch(self):
        serial = Serial(self.status(token=99)); board = client.DPRBoard(serial_port=serial)
        with self.assertRaises(RuntimeError): board.switch({'build_token': 77}, 'blank')
        self.assertNotIn(b'DPR1\2', serial.writes)
    def test_device_error_propagates(self):
        board = client.DPRBoard(serial_port=Serial(b'DPRE' + struct.pack('<I', 14)))
        with self.assertRaisesRegex(RuntimeError, '14'): board.magic(b'DPRR')
    def test_wrong_generation_rejected(self):
        target = client.ARCH
        reply = b'DPRR' + struct.pack('<7I7Q', 2, target, 77, 5, 1000, 16, 0x3000, 10, 100, 20, 140, 130, 50, 200)
        board = client.DPRBoard(serial_port=Serial(self.status() + reply))
        with self.assertRaises(RuntimeError): board.switch({'build_token': 77, 'modules': {client.TARGET: {'id': target, 'partial_bytes': 16}}}, client.TARGET)
    def test_image_family_hash_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp); data = bytes.fromhex('ffffffff665599aa00000020')
            modules = {}
            for name, ident in package.MODULES.items():
                (path / (name + '.bin')).write_bytes(data); (path / (name + '.bit')).write_bytes(b'fixture')
                modules[name] = {'id': ident, 'partial_file': name + '.bin', 'partial_bytes': len(data),
                    'partial_sha256': hashlib.sha256(data).hexdigest(), 'full_file': name + '.bit',
                    'full_sha256': hashlib.sha256(b'fixture').hexdigest()}
            manifest = path / 'images.json'
            manifest.write_text(json.dumps({'schema': 'ldacs_dpr_image_family_v1', 'pr_verify_passed': True,
                'part': 'xc7z010clg400-1', 'build_token': 77, 'modules': modules}))
            self.assertEqual(client.family(manifest)['build_token'], 77)
            (path / 'hybrid.bin').write_bytes(b'changed')
            with self.assertRaises(ValueError): client.family(manifest)
if __name__ == '__main__': unittest.main()

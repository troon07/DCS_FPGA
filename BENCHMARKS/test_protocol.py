"""Protocol/comparison unit fixtures only. These are NOT hardware measurements."""
import copy
import importlib.util
from pathlib import Path
import struct
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'FULL_PS/host'))
sys.path.insert(0, str(ROOT / 'BENCHMARKS'))
import board_client as client
from compare import compare

class FakeSerial:
    def __init__(self, data): self.data, self.written = bytearray(data), b''
    def read(self, n):
        n = min(n, 3)  # Deliberately fragment every response.
        data = bytes(self.data[:n]); del self.data[:n]; return data
    def write(self, data): self.written = data; return len(data)
    def reset_input_buffer(self): pass
    def flush(self): pass
    def close(self): pass

class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.layout, cls.payload, cls.tx = client.prepare('qpsk_1_2')
    def frame(self, arch=2, bad=0, length=None):
        length = len(self.payload) if length is None else length
        return client.RESPONSE.pack(b'LDBR', arch, 0, 2, length, 1, 100, 0 if arch == 2 else 50,
                                    0, 0, bad, 10, 20, 30, 40, 50, 320, 150, 170, 0 if arch == 2 else 100) + self.payload
    def run_frame(self, frame, arch=2):
        board = client.Board(serial_port=FakeSerial(frame))
        return board.benchmark(self.layout, self.payload, self.tx, 2, 1, arch)
    def test_fragmented_response(self):
        result = self.run_frame(self.frame())
        self.assertTrue(result['valid']); self.assertEqual(result['decoder_ticks_sum'], 320)
        self.assertIsNone(result['pl_pipeline_mean_us'])
    def test_wrong_architecture(self):
        with self.assertRaises(RuntimeError): self.run_frame(self.frame(1))
    def test_wrong_lengths(self):
        with self.assertRaises(RuntimeError): self.run_frame(self.frame(length=4))
    def test_each_iteration_crc_failure_invalidates_batch(self):
        result = self.run_frame(self.frame(bad=1))
        self.assertTrue(result['last_output_matches']); self.assertFalse(result['valid'])
    def test_error_frame(self):
        with self.assertRaises(RuntimeError): self.run_frame(b'\xff' * 4)
    def test_timeout(self):
        board = client.Board(timeout=-1, serial_port=FakeSerial(b''))
        with self.assertRaises(TimeoutError): board.read(4)
    def test_trace_order_and_buffers(self):
        dec = client.L.decode_frame(self.tx, self.layout)
        nrs = self.layout['num_cw'] * self.layout['rs_n']
        buffers = [bytes(dec['vit_in']), dec['viterbi_bytes'], dec['block_deinterleaved'], dec['hw_out'], dec['payload']]
        response = b'TRC4\x02' + struct.pack('<7H8I', len(self.tx), nrs, nrs, len(self.payload), len(self.payload),
                                            0, 0, 1, 2, 3, 4, 99, 5, 123, 100) + b''.join(buffers)
        result = client.Board(serial_port=FakeSerial(response)).trace(self.layout, self.payload, self.tx)
        self.assertTrue(result['payload_matches_input'])
        self.assertEqual(result['stage_ticks_gt_equivalent'], [1, 2, 3, 4, 5])
        self.assertTrue(all(s['matches_model'] for s in result['stages'].values()))
    def fixtures(self):
        docs = []
        for arch, name in client.ARCH_NAMES.items():
            sample = self.run_frame(self.frame(arch), arch)
            docs.append({'schema': 'ldacs_partition_benchmark_v1', 'valid': True, 'architecture': name,
                         'seed': 91, 'iterations_per_batch': 2, 'warmups_per_batch': 1, 'batches': 1,
                         'cache_policy': 'fixture', 'decoder_scope': 'fixture', 'board_label': 'fixture',
                         'artifacts': {'firmware': {'sha256': 'fixture'}, 'bitstream': {'sha256': 'fixture'},
                                       'reference_model': {'sha256': 'fixture'},
                                       'firmware_build': {'compiler': 'fixture', 'elf_sha256': 'fixture', 'flags': ['-O2']}},
                         'results': [{'mode': 'qpsk_1_2', 'payload_sha256': 'fixture', 'encoded_frame_sha256': 'fixture',
                                      'layout': self.layout, 'samples': [sample]}]})
        return docs
    def test_comparison_requires_identical_frames(self):
        docs = self.fixtures(); self.assertEqual(len(compare(docs)), 3)
        docs[1]['results'][0]['encoded_frame_sha256'] = 'different'
        with self.assertRaises(ValueError): compare(docs)
    def test_comparison_rejects_different_clocks(self):
        docs = self.fixtures(); docs[1]['results'][0]['samples'][0]['global_timer_hz'] += 1
        with self.assertRaises(ValueError): compare(docs)
    def test_comparison_rejects_missing_provenance(self):
        docs = self.fixtures(); docs[0]['artifacts']['firmware']['sha256'] = None
        with self.assertRaises(ValueError): compare(docs)
    def test_comparison_rejects_compiler_flag_difference(self):
        docs = self.fixtures(); docs[1]['artifacts']['firmware_build']['flags'] = ['-O3']
        with self.assertRaises(ValueError): compare(docs)

if __name__ == '__main__': unittest.main()

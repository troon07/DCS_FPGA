"""Six-way comparison fixtures; no records are saved as real hardware data."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'DPR'))
import compare_six
spec = importlib.util.spec_from_file_location('protocol_fixtures', ROOT / 'BENCHMARKS/test_protocol.py')
fixtures = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixtures)

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixtures.ProtocolTests.setUpClass()
    def documents(self):
        static = fixtures.ProtocolTests().fixtures()
        dynamic = copy.deepcopy(static)
        for arch, d in enumerate(dynamic):
            d['architecture'] = 'DPR_' + d['architecture']; d['schema'] = 'ldacs_dpr_benchmark_v1'
            d['image_family'] = {'build_token': 77, 'pr_verify_passed': True}
            alternate = 3 if arch == 2 else 2
            d['switches'] = [
                {'measurement': 'real_board_pcap_partial_switch', 'build_token': 77, 'from_id': arch,
                 'to_id': alternate, 'microseconds': {'total': 100, 'service_total': 120}},
                {'measurement': 'real_board_pcap_partial_switch', 'build_token': 77, 'from_id': alternate,
                 'to_id': arch, 'microseconds': {'total': 200, 'service_total': 230}, 'post_switch_decode': {'valid': True}}]
            for row in d['results']:
                for sample in row['samples']:
                    sample['execution_platform'] = d['architecture']
                    sample['raw_response_header_hex'] = '44444252' + sample['raw_response_header_hex'][8:]
        return static + dynamic
    def test_complete_six_way_comparison(self):
        rows = compare_six.compare(self.documents())
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r['switch_roundtrip_mean_us'] == 350 for r in rows if r['architecture'].startswith('DPR_')))
    def test_static_response_cannot_be_relabelled(self):
        docs = self.documents(); docs[3]['results'][0]['samples'][0]['raw_response_header_hex'] = '4c444252'
        with self.assertRaises(ValueError): compare_six.compare(docs)
    def test_switch_correctness_required(self):
        docs = self.documents(); docs[3]['switches'][1]['post_switch_decode']['valid'] = False
        with self.assertRaises(ValueError): compare_six.compare(docs)
    def test_all_six_configurations_required(self):
        with self.assertRaises(ValueError): compare_six.compare(self.documents()[:-1])
if __name__ == '__main__': unittest.main()

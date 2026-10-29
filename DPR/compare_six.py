#!/usr/bin/env python3
"""Compare three static and three DPR board captures without inventing missing data."""
import argparse
import copy
import csv
import importlib.util
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('static_compare', ROOT / 'BENCHMARKS/compare.py')
static_compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(static_compare)

def compare(documents):
    names = {'HYBRID', 'FULL_PL', 'FULL_PS', 'DPR_HYBRID', 'DPR_FULL_PL', 'DPR_FULL_PS'}
    if len(documents) != 6 or {d['architecture'] for d in documents} != names:
        raise ValueError('Supply exactly one successful capture for each of the six configurations')
    static = [d for d in documents if not d['architecture'].startswith('DPR_')]
    dynamic = [d for d in documents if d['architecture'].startswith('DPR_')]
    for d in dynamic:
        if d.get('schema') != 'ldacs_dpr_benchmark_v1' or not d.get('switches'):
            raise ValueError('DPR capture must contain actual partial-switch measurements')
        if not d['image_family'].get('pr_verify_passed'): raise ValueError('Unverified image family')
        for t in d['switches']:
            if t.get('measurement') != 'real_board_pcap_partial_switch' or t['build_token'] != d['image_family']['build_token']:
                raise ValueError('Invalid partial-switch provenance')
        for r in d['results']:
            for s in r['samples']:
                if s.get('execution_platform') != d['architecture'] or not s['raw_response_header_hex'].startswith('44444252'):
                    raise ValueError('Static response cannot be labeled as a DPR decoder measurement')
        for t in d['switches'][1::2]:
            if not t.get('post_switch_decode', {}).get('valid'): raise ValueError('Post-switch decoding was not verified')
    # Validate each triple with the existing shared frame/clock/compiler checks.
    normalized = copy.deepcopy(dynamic)
    for d in normalized:
        d['architecture'] = d['architecture'][4:]
        d['schema'] = 'ldacs_partition_benchmark_v1'
    rows = static_compare.compare(static)
    drows = static_compare.compare(normalized)
    # Also validate every static/DPR pair against the same reference triple.
    for d in normalized:
        triple = [d if s['architecture'] == d['architecture'] else s for s in static]
        static_compare.compare(triple)
    for r in drows: r['architecture'] = 'DPR_' + r['architecture']
    rows += drows
    for row in rows:
        ps = next(r for r in rows if r['mode'] == row['mode'] and r['architecture'] == 'FULL_PS')
        row['speedup_vs_static_full_ps'] = ps['decoder_mean_us'] / row['decoder_mean_us']
        row['switch_mean_us'] = None
        row['switch_roundtrip_mean_us'] = None
        row['switch_service_mean_us'] = None
        row['static_pair_decoder_overhead_pct'] = None
        if row['architecture'].startswith('DPR_'):
            d = next(d for d in dynamic if d['architecture'] == row['architecture'])
            switches = d['switches']
            if len(switches) % 2: raise ValueError('Incomplete switch round trip')
            total = sum(t['microseconds']['total'] for t in switches)
            row['switch_mean_us'] = total / len(switches)
            row['switch_service_mean_us'] = sum(t['microseconds']['service_total'] for t in switches) / len(switches)
            row['switch_roundtrip_mean_us'] = sum(t['microseconds']['service_total'] for t in switches) / (len(switches) // 2)
            pair = next(r for r in rows if r['mode'] == row['mode'] and r['architecture'] == row['architecture'][4:])
            row['static_pair_decoder_overhead_pct'] = (row['decoder_mean_us'] / pair['decoder_mean_us'] - 1) * 100
    return rows

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('captures', nargs=6, type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--frames-per-switch-roundtrip', type=int)
    a = p.parse_args()
    rows = compare([json.loads(p.read_text(encoding='utf-8')) for p in a.captures])
    if a.frames_per_switch_roundtrip is not None:
        if a.frames_per_switch_roundtrip <= 0: p.error('Frame count must be positive')
        for row in rows:
            row['amortized_decoder_plus_switch_us'] = row['decoder_mean_us'] + (row['switch_roundtrip_mean_us'] or 0) / a.frames_per_switch_roundtrip
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    report = '| Mode | Configuration | Decode mean us | Payload Mb/s | Speedup vs static PS |\n|---|---|---:|---:|---:|\n'
    for row in rows:
        report += f"| {row['mode']} | {row['architecture']} | {row['decoder_mean_us']:.3f} | {row['payload_mbps']:.6f} | {row['speedup_vs_static_full_ps']:.3f} |\n"
    report += '\nSwitching is a separate measurement. Amortization, if requested, is a workload calculation, not an additional board observation.\n'
    a.output.with_suffix('.md').write_text(report, encoding='utf-8')
    print('Saved six-way comparison:', a.output)
if __name__ == '__main__': main()

#!/usr/bin/env python3
"""Compare compatible, verified board captures. Never fills missing measurements."""
import argparse
import csv
import json
from pathlib import Path

def compare(documents):
    variants = {d['architecture'] for d in documents}
    if variants != {'HYBRID', 'FULL_PL', 'FULL_PS'} or len(documents) != 3:
        raise ValueError('Supply exactly one capture for each of HYBRID, FULL_PL and FULL_PS')
    first = documents[0]
    for d in documents:
        if d.get('schema') != 'ldacs_partition_benchmark_v1' or not d.get('valid'):
            raise ValueError('Only successful board benchmark captures can be compared')
        for field in ('seed', 'iterations_per_batch', 'warmups_per_batch', 'batches', 'cache_policy', 'decoder_scope'):
            if d[field] != first[field]: raise ValueError(f'Incompatible benchmark setting: {field}')
        if d.get('board_label') != first.get('board_label'): raise ValueError('Board identities differ')
        for key in ('firmware', 'bitstream', 'reference_model'):
            if not d['artifacts'][key]['sha256']: raise ValueError(f'Missing local artifact provenance: {key}')
        if not d['artifacts'].get('firmware_build'): raise ValueError('Missing firmware compiler/source metadata')
        build = d['artifacts']['firmware_build']
        if build['elf_sha256'] != d['artifacts']['firmware']['sha256']:
            raise ValueError('Firmware ELF does not match its build metadata')
        if build['compiler'] != first['artifacts']['firmware_build']['compiler']:
            raise ValueError('Use the same firmware compiler for all architectures')
        def common_flags(metadata):
            return [f for f in metadata['flags'] if not f.endswith('.c') and not f.startswith('-DARCH=')]
        if common_flags(build) != common_flags(first['artifacts']['firmware_build']):
            raise ValueError('Firmware compiler flags differ across architectures')
        if d['artifacts']['reference_model']['sha256'] != first['artifacts']['reference_model']['sha256']:
            raise ValueError('Reference model differs across architectures')
        if {r['mode'] for r in d['results']} != {r['mode'] for r in first['results']}:
            raise ValueError('Mode sets differ across captures')
    rows = []
    for original in first['results']:
        mode = original['mode']
        mode_rows = []
        for d in documents:
            matches = [r for r in d['results'] if r['mode'] == mode]
            if len(matches) != 1: raise ValueError('Duplicate or missing mode')
            row = matches[0]
            for key in ('payload_sha256', 'encoded_frame_sha256', 'layout'):
                if row[key] != original[key]: raise ValueError(f'Different frame data or parameters for {mode}')
            samples = row['samples']
            if len(samples) != d['batches']: raise ValueError('Incomplete batch capture')
            if any(s['iterations'] != d['iterations_per_batch'] or s['warmups'] != d['warmups_per_batch']
                   for s in samples): raise ValueError('Repetition settings differ within capture')
            if len({(s['global_timer_hz'], s['pl_clock_hz']) for s in samples}) != 1:
                raise ValueError('Clocks changed between measured batches')
            if any(s.get('measurement') != 'real_board_uart_response' or not s['valid'] or
                   s['architecture'] != d['architecture'] or s['crc_failed_frames'] or s['rs_failures'] or
                   not s['last_output_matches'] for s in samples): raise ValueError('Failed or incompatible board response')
            reps = sum(s['iterations'] for s in samples)
            seconds = sum(s['decoder_ticks_sum'] / s['global_timer_hz'] for s in samples)
            mean_us = seconds * 1e6 / reps
            record = {'mode': mode, 'architecture': d['architecture'], 'frames': reps,
                      'decoder_mean_us': mean_us, 'decoder_min_us': min(s['decoder_min_us'] for s in samples),
                      'decoder_max_us': max(s['decoder_max_us'] for s in samples),
                      'payload_mbps': row['layout']['payload_bytes'] * 8 * reps / seconds / 1e6,
                      'uart_mean_batch_ms': sum(s['uart_batch_wall_ms'] for s in samples) / len(samples),
                      'global_timer_hz': samples[0]['global_timer_hz'], 'pl_clock_hz': samples[0]['pl_clock_hz'],
                      'cpu_clock_hz': samples[0]['global_timer_hz'] * 2}
            resource = d['artifacts'].get('routed_build', {})
            for key in ('lut', 'ff', 'bram', 'dsp', 'wns_ns'): record[key] = resource.get(key)
            for name in ('helical', 'viterbi', 'block_deinterleaver', 'reed_solomon', 'derandomizer'):
                record[name + '_mean_us'] = sum(s['stage_measurements'][name]['ticks_sum'] /
                                              s['stage_measurements'][name]['clock_hz'] * 1e6 for s in samples) / reps
            mode_rows.append(record)
        cpu_hz = {r['cpu_clock_hz'] for r in mode_rows}
        pl_hz = {r['pl_clock_hz'] for r in mode_rows if r['architecture'] != 'FULL_PS'}
        if len(cpu_hz) != 1 or len(pl_hz) != 1: raise ValueError('CPU/PL clocks differ; use a common-clock experiment')
        ps_mean = next(r['decoder_mean_us'] for r in mode_rows if r['architecture'] == 'FULL_PS')
        for r in mode_rows:
            r['speedup_vs_full_ps'] = ps_mean / r['decoder_mean_us']
            rows.append(r)
    return rows

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('captures', type=Path, nargs=3)
    p.add_argument('--output', type=Path, required=True, help='Output CSV; Markdown is saved beside it')
    p.add_argument('--deadline-us', type=float, help='Optional application frame deadline, supplied by the researcher')
    a = p.parse_args()
    rows = compare([json.loads(path.read_text()) for path in a.captures])
    if a.deadline_us is not None:
        if a.deadline_us <= 0: p.error('Deadline must be positive')
        for row in rows:
            row['deadline_us'] = a.deadline_us
            row['all_observed_decodes_meet_deadline'] = row['decoder_max_us'] <= a.deadline_us
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    text = '| Mode | Architecture | Mean decode us | Payload Mb/s | Speedup vs PS |\n|---|---|---:|---:|---:|\n'
    for r in rows:
        text += f"| {r['mode']} | {r['architecture']} | {r['decoder_mean_us']:.3f} | {r['payload_mbps']:.6f} | {r['speedup_vs_full_ps']:.3f} |\n"
    text += '\nStage latencies overlap in PL and must not be added. UART batch times are reported separately in the CSV.\n'
    a.output.with_suffix('.md').write_text(text)
    print(text)

if __name__ == '__main__': main()

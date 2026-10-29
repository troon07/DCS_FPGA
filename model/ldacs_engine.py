#!/usr/bin/env python3
"""
LDACS Physical Layer Transceiver Engine — Real Hardware Edition
==============================================================
Paper: Kurz et al., "High Performance Implementation of Next Generation
       Aeronautical Communication Systems", IEEE OJIES 2022.

TX chain (PC/software):
  Payload -> [1] PRBS Randomize -> [2] RS(101,91) Encode ->
  [3] Block Interleave -> [4] Conv Encode (K=7) -> [5] Helical Interleave
  -> encoded bits -> COM5 -> FPGA

RX chain split:
  encoded bits -> [1-PS] Helical Deinterleave  (Zynq ARM)
  -> [2-HW] Viterbi Decode       (FPGA, 25.23 µs per paper Table 3)
  -> [3-HW] Block Deinterleave   (FPGA,  6.10 µs)
  -> [4-HW] Reed-Solomon Decode  (FPGA,  9.10 µs)
  -> [5-PS] PRBS Derandomize     (Zynq ARM)
  -> via COM5 back to PC
  -> Recovered payload

Hardware path: pyserial -> COM5 -> uart_bridge.elf on Zynq ARM -> AXI DMA ->
               FPGA IP (Viterbi + Block Deint + RS) -> DMA -> uart_bridge -> COM5

Paper performance reference (Table 3, Table 4, qpsk_1_2 mode):
  Stage timing (µs):   Helical=227.44, Viterbi=25.23, BlockDeint=6.10,
                       RS=9.10, Derand=19.56, DMA=336.26, Total=623.69
  Throughput:          15.58 Mb/s  (required: 0.75 Mb/s, factor: 20.72x)
  Tolerable BER:       6.65% (650 bits per 9768-bit block)
"""

import os
import sys
import time
import subprocess
import struct
import threading
import hashlib
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from model.ldacs_ref import (
    MODES, RATE_CODE, TAIL_BITS, RS_N, RS_NSYM, HELICAL_ROWS,
    frame_layout, randomize, rs_encode, rs_decode,
    block_interleave, block_deinterleave, conv_encode_punct, viterbi_decode,
    helical_interleave, helical_deinterleave, bytes_to_bits, bits_to_bytes,
    decode_frame
)

XSDB_PATH    = r"C:\Xilinx\Vitis\2022.2\bin\xsdb.bat"
BOOT_TCL     = os.path.join(BASE_DIR, "boot_firmware.tcl")
COM_PORT     = "COM5"
BAUD_RATE    = 115200
UART_TIMEOUT = 8.0   # seconds — generous for first frame boot

# ── Paper Table 3: per-stage timing reference (µs, HW/SW codesign, qpsk_1_2) ──
PAPER_TIMING_US = {
    "helical_deint_sw": 227.44,
    "viterbi_hw":        25.23,
    "block_deint_hw":     6.10,
    "rs_hw":              9.10,
    "derand_sw":         19.56,
    "dma_framework":    336.26,
    "total_per_block":  623.69,
    "super_frame":    11581.0,
}

# ── Paper Table 4: throughput reference (Mb/s) ──
PAPER_THROUGHPUT = {
    "qpsk_1_2":   {"achieved": 15.58, "required": 0.75,  "rt_factor": 20.72},
    "qpsk_2_3":   {"achieved": 15.16, "required": 0.75,  "rt_factor": 20.16},
    "qpsk_3_4":   {"achieved": 14.95, "required": 0.75,  "rt_factor": 19.88},
    "16qam_1_2":  {"achieved": 20.82, "required": 1.48,  "rt_factor": 14.02},
    "16qam_2_3":  {"achieved": 20.09, "required": 1.48,  "rt_factor": 13.53},
    "64qam_1_2":  {"achieved": 23.53, "required": 2.22,  "rt_factor": 10.61},
    "64qam_2_3":  {"achieved": 22.53, "required": 2.22,  "rt_factor": 10.16},
    "64qam_3_4":  {"achieved": 22.06, "required": 2.22,  "rt_factor":  9.95},
}

# ── Paper Table 2: tolerable error bits per block ──
PAPER_TOLERABLE_ERRORS = {
    "qpsk_1_2":  {"bits": 650,  "pct": 6.65},
    "qpsk_2_3":  {"bits": 300,  "pct": 3.07},
    "qpsk_3_4":  {"bits": 150,  "pct": 1.54},
    "16qam_1_2": {"bits": 1400, "pct": 7.17},
    "16qam_2_3": {"bits": 600,  "pct": 3.07},
    "64qam_1_2": {"bits": 1900, "pct": 6.48},
    "64qam_2_3": {"bits": 900,  "pct": 3.07},
    "64qam_3_4": {"bits": 500,  "pct": 1.71},
}

# ── Paper Table 1: FPGA resource utilization ──
PAPER_UTILIZATION = {
    "viterbi":       {"lut_logic": 3647, "lut_mem": 26,  "ff": 2409, "lut_pct": 1.70},
    "block_deint":   {"lut_logic": 152,  "lut_mem": 12,  "ff": 211,  "lut_pct": 0.07},
    "rs_decoder":    {"lut_logic": 1476, "lut_mem": 89,  "ff": 1403, "lut_pct": 0.69},
    "dma":           {"lut_logic": 2597, "lut_mem": 227, "ff": 4665, "lut_pct": 1.21},
    "total":         {"lut_logic": 7872, "lut_mem": 354, "ff": 8688, "lut_pct": 3.67},
}

# ── Protocol constants ──
MAGIC_TX = b'\x4C\x44\x41\x43'   # "LDAC"
MAGIC_RX = b'\x41\x43\x4C\x44'   # "ACLD"
MAGIC_RX_TRACE = b'TRC3'            # real board stage traces + measured cycles
MAGIC_ERR = b'\xFF\xFF\xFF\xFF'

def format_hex_preview(data, max_bytes=64):
    if isinstance(data, (list, tuple)):
        data = bytes(data)
    elif isinstance(data, str):
        data = data.encode('utf-8')
    h = data[:max_bytes].hex().upper()
    return " ".join(h[i:i+2] for i in range(0, len(h), 2)) + (" ..." if len(data) > max_bytes else "")


def format_stage_output(data, representation="hex"):
    """Serialize a real stage buffer with full output, preview, and digest."""
    raw = bytes(data)
    if representation == "bits":
        full = "".join("1" if value else "0" for value in raw)
        preview = full[:256] + (" ..." if len(full) > 256 else "")
        unit = "bits"
    else:
        full = raw.hex(" ").upper()
        preview = " ".join(f"{value:02X}" for value in raw[:64])
        if len(raw) > 64:
            preview += " ..."
        unit = "bytes"
    return {
        "length": len(raw),
        "unit": unit,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "preview": preview,
        "full_output": full,
    }


def make_trace_stage(name, data, representation, source, comparison=None):
    stage = format_stage_output(data, representation)
    stage.update({"name": name, "source": source})
    if comparison is not None:
        stage["comparison"] = comparison
    return stage


def compare_stage_buffers(reference, observed):
    reference = bytes(reference)
    observed = bytes(observed)
    mismatch_count = sum(a != b for a, b in zip(reference, observed)) + abs(len(reference) - len(observed))
    return {
        "match": mismatch_count == 0,
        "mismatch_count": mismatch_count,
        "reference_length": len(reference),
        "observed_length": len(observed),
    }


def _parse_resource_report(path):
    """Read routed Vivado resource counts; return None when no real report exists."""
    if not os.path.isfile(path):
        return None
    text = open(path, "r", encoding="utf-8", errors="replace").read()
    patterns = {
        "lut": r"\|\s*Slice LUTs\s*\|\s*([0-9.]+)",
        "ff": r"\|\s*Slice Registers\s*\|\s*([0-9.]+)",
        "bram": r"\|\s*Block RAM Tile\s*\|\s*([0-9.]+)",
        "dsp": r"\|\s*DSPs\s*\|\s*([0-9.]+)",
    }
    result = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        result[key] = float(match.group(1)) if match else None
        if result[key] is not None and result[key].is_integer():
            result[key] = int(result[key])
    return result if any(value is not None for value in result.values()) else None


def _parse_timing_report(path):
    """Read the first (worst setup) routed path slack from a Vivado report."""
    if not os.path.isfile(path):
        return None
    text = open(path, "r", encoding="utf-8", errors="replace").read()
    match = re.search(r"Slack \((?:MET|VIOLATED)\)\s*:\s*([-+0-9.]+)ns", text)
    return {"worst_setup_slack_ns": float(match.group(1))} if match else None


def load_vivado_build_metrics(base_dir=BASE_DIR):
    """Load only metrics emitted by the current routed Vivado build."""
    report_dir = os.path.join(base_dir, "hw", "vivado", "build")
    blocks = []
    for key, label in (
        ("viterbi", "Viterbi decoder"),
        ("block_deint", "Block deinterleaver"),
        ("rs_decoder", "Reed-Solomon decoder"),
        ("decoder", "Complete decoder IP"),
    ):
        utilization = _parse_resource_report(os.path.join(report_dir, f"utilization_{key}.rpt"))
        timing = _parse_timing_report(os.path.join(report_dir, f"timing_{key}.rpt"))
        blocks.append({
            "name": label,
            "utilization": utilization,
            "static_timing": timing,
            "available": utilization is not None or timing is not None,
        })
    return {
        "source": "Current Vivado routed-design reports",
        "total": _parse_resource_report(os.path.join(report_dir, "utilization.rpt")),
        "blocks": blocks,
    }


def measured_stage(name, domain, elapsed_us, work_size, work_unit, cycles=None):
    work_bits = work_size if work_unit == "bits" else work_size * 8
    return {
        "name": name,
        "domain": domain,
        "latency_us": round(elapsed_us, 3),
        "cycles": cycles,
        "work_size": work_size,
        "work_unit": work_unit,
        "throughput_mbps": round(work_bits / max(elapsed_us, 0.001), 6),
        "source": "Measured during this transaction",
    }


class LDACSEngine:
    def __init__(self, base_dir=BASE_DIR):
        self.base_dir = base_dir
        self.last_result = None
        self.hw_connected = False
        self.firmware_booted = False
        self._serial = None
        self._serial_lock = threading.Lock()

    # ──────────────────────────────────────────────────────────────────────
    # PUBLIC: process one transmission frame end-to-end
    # ──────────────────────────────────────────────────────────────────────
    def process_transmission(self, input_text, mode="qpsk_1_2"):
        lay = frame_layout(mode)
        payload_target_len = lay["payload_bytes"]

        # ── Payload framing ──────────────────────────────────────────────
        t0 = time.perf_counter_ns()
        raw_bytes = input_text.encode('utf-8')
        orig_text_len = len(raw_bytes)
        if len(raw_bytes) < payload_target_len:
            padded_payload = raw_bytes + b'\x00' * (payload_target_len - len(raw_bytes))
        else:
            padded_payload = raw_bytes[:payload_target_len]
        t_payload = (time.perf_counter_ns() - t0) / 1000.0

        # ── TX STAGE 1: PRBS Randomizer (x^15 + x^14 + 1, SPEC seed 0x4A80) ──
        t0 = time.perf_counter_ns()
        tx1_randomized = randomize(padded_payload)
        t_tx1 = (time.perf_counter_ns() - t0) / 1000.0

        # ── TX STAGE 2: Reed-Solomon RS(101,91), t=5, GF(2^8), poly=0x11D ──
        t0 = time.perf_counter_ns()
        K = lay["rs_k"]
        cws = [rs_encode(tx1_randomized[i * K:(i + 1) * K]) for i in range(lay["num_cw"])]
        tx2_rs = b"".join(cws)
        t_tx2 = (time.perf_counter_ns() - t0) / 1000.0

        # ── TX STAGE 3: Block (byte) interleaver — round-robin across RS codewords ──
        t0 = time.perf_counter_ns()
        tx3_block = block_interleave(cws)
        t_tx3 = (time.perf_counter_ns() - t0) / 1000.0

        # ── TX STAGE 4: Convolutional encoder K=7 G1=0o171 G2=0o133 + puncturing ──
        t0 = time.perf_counter_ns()
        bits = bytes_to_bits(tx3_block) + [0] * lay["pad_bits"] + [0] * TAIL_BITS
        tx4_conv = conv_encode_punct(bits, lay["rate"])
        t_tx4 = (time.perf_counter_ns() - t0) / 1000.0

        # ── TX STAGE 5: Helical interleaver (24 rows, helical-scan permutation) ──
        t0 = time.perf_counter_ns()
        tx5_helical = helical_interleave(tx4_conv)
        t_tx5 = (time.perf_counter_ns() - t0) / 1000.0

        # Hardware-integration validation sends the encoded frame unchanged.
        # Artificial SNR/error injection is deliberately excluded from the
        # live UI because it is generated data, not a board measurement.
        rx_channel_bits = list(tx5_helical)
        n_bits = len(rx_channel_bits)
        injected_errors = 0
        channel_ber = 0.0

        # ── RX STAGES 1–5 (Zynq PS + FPGA via COM5) ────────────────────
        # The PC sends the helical-interleaved bits unchanged.  uart_bridge
        # executes stages 1 and 5 on the Zynq ARM, surrounding stages 2–4 in
        # PL fabric, exactly matching the paper's partition.
        t_hw_start = time.perf_counter()
        hw_res = self._run_fpga_uart(mode, lay, rx_channel_bits)
        t_hw_us = (time.perf_counter() - t_hw_start) * 1e6

        hw_success  = hw_res["success"]
        # A result is valid only when it was returned by uart_bridge after an
        # AXI-DMA transaction.  Never substitute a model/reference result.
        if not hw_success:
            result = self._hardware_failure(mode, input_text, hw_res.get("error", "No FPGA response"))
            self.last_result = result
            self.hw_connected = False
            return result
        hw_out      = hw_res["data"]
        hw_helical  = hw_res["helical_deinterleaved"]
        hw_viterbi  = hw_res["viterbi_bytes"]
        hw_block    = hw_res["block_deinterleaved"]
        hw_rs       = hw_res["rs_decoded"]
        rs_corr     = hw_res.get("rs_corr", 0)
        rs_fail     = hw_res.get("rs_fail", 0)
        hw_cycles   = hw_res["timing_cycles"]
        pl_clock_hz = hw_res["pl_clock_hz"]
        cycle_us    = 1e6 / pl_clock_hz
        self.hw_connected = hw_success

        # uart_bridge returns the final PS-derandomized payload.
        rx5_derand = hw_out
        t_rx1_us = hw_cycles["helical_ps"] * cycle_us
        t_rx5_us = hw_cycles["derandomizer_ps"] * cycle_us

        # Run the complete software receive chain on the exact encoded frame
        # sent to COM5. This is an implementation-consistency comparison only:
        # hardware and software intentionally use the same SPEC-CHECK values.
        t_sw_start = time.perf_counter_ns()
        t0 = time.perf_counter_ns()
        sw_vit_in = helical_deinterleave(rx_channel_bits)
        t_sw_helical = (time.perf_counter_ns() - t0) / 1000.0

        t0 = time.perf_counter_ns()
        sw_bits = viterbi_decode(sw_vit_in, lay["n_steps"], lay["rate"])
        sw_data = bits_to_bytes(sw_bits[:lay["num_cw"] * lay["rs_n"] * 8])
        t_sw_viterbi = (time.perf_counter_ns() - t0) / 1000.0

        t0 = time.perf_counter_ns()
        sw_deinterleaved = b"".join(block_deinterleave(sw_data, lay["num_cw"]))
        t_sw_block = (time.perf_counter_ns() - t0) / 1000.0

        t0 = time.perf_counter_ns()
        sw_hw_out, sw_corr, sw_fail = bytearray(), 0, 0
        for offset in range(0, len(sw_deinterleaved), lay["rs_n"]):
            decoded, corrected, ok = rs_decode(sw_deinterleaved[offset:offset + lay["rs_n"]])
            sw_hw_out += decoded
            sw_corr += corrected
            sw_fail += 0 if ok else 1
        t_sw_rs = (time.perf_counter_ns() - t0) / 1000.0

        t0 = time.perf_counter_ns()
        sw_payload = randomize(bytes(sw_hw_out))
        t_sw_derand = (time.perf_counter_ns() - t0) / 1000.0
        t_sw_decode_us = (time.perf_counter_ns() - t_sw_start) / 1000.0
        sw_dec = {
            "vit_in": sw_vit_in,
            "viterbi_bytes": sw_data,
            "block_deinterleaved": sw_deinterleaved,
            "hw_out": bytes(sw_hw_out),
            "payload": sw_payload,
            "n_corr": sw_corr,
            "n_fail": sw_fail,
        }
        hw_sw_byte_mismatches = (
            sum(a != b for a, b in zip(rx5_derand, sw_payload))
            + abs(len(rx5_derand) - len(sw_payload))
        )
        sw_input_byte_mismatches = (
            sum(a != b for a, b in zip(padded_payload, sw_payload))
            + abs(len(padded_payload) - len(sw_payload))
        )

        software_decoder_buffers = {
            "helical": bytes(sw_dec["vit_in"]),
            "viterbi": sw_dec["viterbi_bytes"],
            "block": sw_dec["block_deinterleaved"],
            "rs": sw_dec["hw_out"],
            "final": sw_dec["payload"],
        }
        board_decoder_buffers = {
            "helical": hw_helical,
            "viterbi": hw_viterbi,
            "block": hw_block,
            "rs": hw_rs,
            "final": rx5_derand,
        }
        stage_comparisons = {
            name: compare_stage_buffers(software_decoder_buffers[name], board_decoder_buffers[name])
            for name in software_decoder_buffers
        }

        # ── Recovered text ───────────────────────────────────────────────
        recovered_trimmed = rx5_derand[:orig_text_len]
        try:
            recovered_text = recovered_trimmed.decode('utf-8')
        except UnicodeDecodeError:
            recovered_text = recovered_trimmed.decode('latin1', errors='replace')

        # ── Metrics ──────────────────────────────────────────────────────
        byte_mismatches = sum(1 for a, b in zip(padded_payload, rx5_derand) if a != b)
        bit_mismatches  = sum((a ^ b).bit_count() for a, b in zip(padded_payload, rx5_derand))
        char_mismatches = sum(1 for a, b in zip(raw_bytes, recovered_trimmed) if a != b)
        residual_ber    = bit_mismatches / float(payload_target_len * 8)

        # All timing below comes from this UART/FPGA transaction.
        t_total_us = t_hw_us
        payload_bits = payload_target_len * 8
        hw_throughput_mbps   = payload_bits / max(t_hw_us, 1.0)
        link_throughput_mbps = payload_bits / max(t_total_us, 1.0)
        latency_ms_display   = round(t_total_us / 1000.0, 3)

        n_rs_bytes = lay["num_cw"] * lay["rs_n"]
        software_encoder_performance = [
            measured_stage("Payload framing", "Host software", t_payload, payload_target_len, "bytes"),
            measured_stage("PRBS randomizer", "Host software", t_tx1, payload_target_len, "bytes"),
            measured_stage("Reed-Solomon encoder", "Host software", t_tx2, len(tx2_rs), "bytes"),
            measured_stage("Block interleaver", "Host software", t_tx3, len(tx3_block), "bytes"),
            measured_stage("Convolutional encoder", "Host software", t_tx4, len(tx4_conv), "bits"),
            measured_stage("Helical interleaver", "Host software", t_tx5, len(tx5_helical), "bits"),
        ]
        software_decoder_performance = [
            measured_stage("Helical deinterleaver", "Host software reference", t_sw_helical, n_bits, "bits"),
            measured_stage("Viterbi decoder", "Host software reference", t_sw_viterbi, n_rs_bytes, "bytes"),
            measured_stage("Block deinterleaver", "Host software reference", t_sw_block, n_rs_bytes, "bytes"),
            measured_stage("Reed-Solomon decoder", "Host software reference", t_sw_rs, payload_target_len, "bytes"),
            measured_stage("PRBS derandomizer", "Host software reference", t_sw_derand, payload_target_len, "bytes"),
        ]
        board_decoder_performance = [
            measured_stage("Helical deinterleaver", "Zynq ARM PS", t_rx1_us, n_bits, "bits", hw_cycles["helical_ps"]),
            measured_stage("Viterbi decoder", "XC7Z010 FPGA PL", hw_cycles["viterbi_pl"] * cycle_us, n_rs_bytes, "bytes", hw_cycles["viterbi_pl"]),
            measured_stage("Block deinterleaver", "XC7Z010 FPGA PL", hw_cycles["block_pl"] * cycle_us, n_rs_bytes, "bytes", hw_cycles["block_pl"]),
            measured_stage("Reed-Solomon decoder", "XC7Z010 FPGA PL", hw_cycles["rs_pl"] * cycle_us, payload_target_len, "bytes", hw_cycles["rs_pl"]),
            measured_stage("PRBS derandomizer", "Zynq ARM PS", t_rx5_us, payload_target_len, "bytes", hw_cycles["derandomizer_ps"]),
        ]


        result = {
            "status": "success",
            "mode": mode,
            "hw_active": hw_success,
            "hw_mode_desc": "COM5 response received after PS/PL DMA transaction",
            "device": "xc7z010clg400-1",
            "clock_mhz": 71.429,
            "input_text": input_text,
            "recovered_text": recovered_text,
            "orig_length_bytes": orig_text_len,
            "frame_payload_bytes": payload_target_len,
            "coded_bits": lay["coded_bits"],
            "num_codewords": lay["num_cw"],
            "rs_n": lay["rs_n"],
            "rs_k": lay["rs_k"],
            "trellis_steps": lay["n_steps"],
            "injected_errors": injected_errors,
            "channel_ber": round(channel_ber, 6),
            "residual_ber": round(residual_ber, 6),
            "byte_mismatches": byte_mismatches,
            "bit_mismatches": bit_mismatches,
            "char_mismatches": char_mismatches,
            "rs_corrections": rs_corr,
            "rs_fails": rs_fail,
            "is_bit_exact": (bit_mismatches == 0),
            "hardware_evidence": {
                "port": COM_PORT,
                "baud": BAUD_RATE,
                "response_received": True,
                "path": "PC -> COM5 -> Zynq PS -> AXI DMA -> FPGA PL -> AXI DMA -> Zynq PS -> COM5 -> PC",
                "measurement_scope": "Per-stage PL-clock counters plus UART-to-UART host wall clock",
            },
            "software_crosscheck": {
                "executed": True,
                "scope": "Full software RX chain on the exact encoded frame sent to hardware",
                "matches_hardware": hw_sw_byte_mismatches == 0,
                "hardware_vs_software_byte_mismatches": hw_sw_byte_mismatches,
                "software_matches_input": sw_input_byte_mismatches == 0,
                "software_vs_input_byte_mismatches": sw_input_byte_mismatches,
                "software_rs_corrections": sw_dec["n_corr"],
                "software_rs_failures": sw_dec["n_fail"],
                "measured_decode_ms": round(t_sw_decode_us / 1000.0, 3),
                "measured_payload_throughput_mbps": round(payload_bits / max(t_sw_decode_us, 1.0), 6),
                "limitation": "Uses the same SPEC-CHECK constants as hardware; this validates implementation agreement, not specification conformance",
            },
            "trace_columns": {
                "software_encoder": [
                    make_trace_stage("Payload and framing", padded_payload, "hex", "Host software encoder"),
                    make_trace_stage("PRBS randomizer", tx1_randomized, "hex", "Host software encoder"),
                    make_trace_stage("Reed-Solomon encoder", tx2_rs, "hex", "Host software encoder"),
                    make_trace_stage("Block interleaver", tx3_block, "hex", "Host software encoder"),
                    make_trace_stage("Convolutional encoder", tx4_conv, "bits", "Host software encoder"),
                    make_trace_stage("Helical interleaver / transmitted frame", tx5_helical, "bits", "Exact frame sent to COM5"),
                ],
                "software_decoder": [
                    make_trace_stage("Helical deinterleaver", software_decoder_buffers["helical"], "bits", "Full software decoder"),
                    make_trace_stage("Viterbi decoder", software_decoder_buffers["viterbi"], "hex", "Full software decoder"),
                    make_trace_stage("Block deinterleaver", software_decoder_buffers["block"], "hex", "Full software decoder"),
                    make_trace_stage("Reed-Solomon decoder", software_decoder_buffers["rs"], "hex", "Full software decoder"),
                    make_trace_stage("PRBS derandomizer / recovered payload", software_decoder_buffers["final"], "hex", "Full software decoder"),
                ],
                "board_decoder": [
                    make_trace_stage("Helical deinterleaver", board_decoder_buffers["helical"], "bits", "Zynq ARM PS via COM5", stage_comparisons["helical"]),
                    make_trace_stage("Viterbi decoder", board_decoder_buffers["viterbi"], "hex", "XC7Z010 FPGA PL trace tap", stage_comparisons["viterbi"]),
                    make_trace_stage("Block deinterleaver", board_decoder_buffers["block"], "hex", "XC7Z010 FPGA PL trace tap", stage_comparisons["block"]),
                    make_trace_stage("Reed-Solomon decoder", board_decoder_buffers["rs"], "hex", "XC7Z010 FPGA PL trace tap", stage_comparisons["rs"]),
                    make_trace_stage("PRBS derandomizer / hardware payload", board_decoder_buffers["final"], "hex", "Zynq ARM PS via COM5", stage_comparisons["final"]),
                ],
            },

            "performance_analysis": {
                "measurement_status": "Real measurements from this transaction and current routed build",
                "pl_clock_hz": pl_clock_hz,
                "pl_clock_mhz": round(pl_clock_hz / 1e6, 6),
                "clock_period_ns": round(1e9 / pl_clock_hz, 6),
                "software_encoder": software_encoder_performance,
                "software_decoder": software_decoder_performance,
                "board_decoder": board_decoder_performance,
                "complete_pl_pipeline": measured_stage(
                    "Complete FPGA pipeline", "XC7Z010 FPGA PL",
                    hw_cycles["pipeline_pl"] * cycle_us,
                    payload_target_len, "bytes", hw_cycles["pipeline_pl"]),
                "board_processing": measured_stage(
                    "Board processing (three trace passes)", "Zynq PS + FPGA PL",
                    hw_cycles["board_processing"] * cycle_us,
                    payload_target_len, "bytes", hw_cycles["board_processing"]),
                "uart_round_trip": {
                    "name": "Complete COM5 trace transaction",
                    "domain": "PC + UART + PS + DMA + PL",
                    "latency_us": round(t_hw_us, 3),
                    "cycles": None,
                    "work_size": payload_target_len,
                    "work_unit": "bytes",
                    "throughput_mbps": round(payload_bits / max(t_hw_us, 0.001), 6),
                    "source": "Measured host wall clock during this transaction",
                },
                "vivado": load_vivado_build_metrics(self.base_dir),
                "notes": [
                    "FPGA and ARM times use the board's free-running PL clock counter.",
                    "The complete COM5 transaction includes UART transfer of all trace buffers and is not pure decoder latency.",
                    "Utilization and static timing are build-time measurements from the current routed Vivado reports.",
                ],
            },

            # ── Timing: measured (µs) ──
            "timing_us": {
                "payload_framing_us": round(t_payload, 2),
                "tx1_prbs_us":      round(t_tx1, 2),
                "tx2_rs_enc_us":    round(t_tx2, 2),
                "tx3_block_int_us": round(t_tx3, 2),
                "tx4_conv_enc_us":  round(t_tx4, 2),
                "tx5_helical_int_us": round(t_tx5, 2),
                "rx1_helical_deint_us": round(t_rx1_us, 2),
                "rx2_viterbi_us": round(hw_cycles["viterbi_pl"] * cycle_us, 2),
                "rx3_block_deint_us": round(hw_cycles["block_pl"] * cycle_us, 2),
                "rx4_rs_us": round(hw_cycles["rs_pl"] * cycle_us, 2),
                "rx_hw_total_us":   round(t_hw_us, 2),
                "rx5_derand_us":    round(t_rx5_us, 2),
                "total_decode_us":  round(t_total_us, 2),
            },

            # ── Throughput: measured (Mb/s) ──
            "throughput_mbps": round(link_throughput_mbps, 3),
            "hw_throughput_mbps": round(hw_throughput_mbps, 3),
            # Wall-clock timing of this real UART/FPGA transaction.
            "latency_ms": latency_ms_display,
            "latency_ms_raw": round(t_total_us / 1000.0, 3),   # actual Python wall-clock (for debug)
            "hw_latency_ms": round(t_hw_us / 1000.0, 3),

            # Legacy keys (kbps) for backwards compat with old frontend
            "throughput_kbps": round(link_throughput_mbps * 1000, 2),
            "hw_throughput_kbps": round(hw_throughput_mbps * 1000, 2),


            # ── 5-Stage TX intermediate data ──
            "tx_stages": {
                "stage1_payload": {
                    "title": "Stage 1 — Input Payload & Framing",
                    "desc": "Layer-2 data padded to frame length",
                    "hex": format_hex_preview(padded_payload),
                    "size_bytes": len(padded_payload),
                    "sample_text": input_text[:40] + ("..." if len(input_text) > 40 else ""),
                    "time_us": round(t_tx1, 2),
                },
                "stage2_prbs": {
                    "title": "Stage 2 — PRBS Randomizer (x¹⁵+x¹⁴+1)",
                    "desc": "Seed: 0x4A80 | XOR with 15-bit LFSR sequence",
                    "hex": format_hex_preview(tx1_randomized),
                    "size_bytes": len(tx1_randomized),
                    "time_us": round(t_tx1, 2),
                },
                "stage3_rs_enc": {
                    "title": "Stage 3 — Reed-Solomon RS(101,91) Encoder",
                    "desc": f"GF(2⁸) poly=0x11D | {lay['num_cw']} codewords | t=5 error correction",
                    "hex": format_hex_preview(tx2_rs),
                    "size_bytes": len(tx2_rs),
                    "parity_bytes": RS_NSYM * lay["num_cw"],
                    "num_cw": lay["num_cw"],
                    "time_us": round(t_tx2, 2),
                },
                "stage4_block_int": {
                    "title": "Stage 4 — Block Byte Interleaver",
                    "desc": "Round-robin distribution across RS codewords",
                    "hex": format_hex_preview(tx3_block),
                    "size_bytes": len(tx3_block),
                    "time_us": round(t_tx3, 2),
                },
                "stage5_conv_helical": {
                    "title": "Stage 5 — Conv Encoder (K=7, G₁=0o171, G₂=0o133) + Helical Interleaver",
                    "desc": f"Rate {lay['rate']} puncturing | {HELICAL_ROWS} rows helical scan | {lay['coded_bits']} coded bits",
                    "coded_bits": len(tx4_conv),
                    "helical_bits": len(tx5_helical),
                    "bit_sample": "".join(str(b) for b in tx5_helical[:64]) + " ...",
                    "time_us": round(t_tx4 + t_tx5, 2),
                },
            },

            # ── 5-Stage RX intermediate data ──
            "rx_stages": {
                "stage1_helical_deint": {
                    "title": "Stage 1 — Helical De-Interleaver [Zynq PS]",
                    "desc": "24-row helical scan inverse; executed by uart_bridge on the Zynq ARM",
                    "coded_bits": len(rx_channel_bits),
                    "bit_sample": format_hex_preview(hw_helical),
                    "measured_us": round(t_rx1_us, 3),
                    "measured_cycles": hw_cycles["helical_ps"],
                    "domain": "ZYNQ PS",
                },
                "stage2_viterbi": {
                    "title": "Stage 2 — Viterbi Trellis Decoder [FPGA]",
                    "desc": f"K=7 hardware Viterbi | {lay['n_steps']} trellis steps",
                    "trellis_steps": lay["n_steps"],
                    "measured_us": round(hw_cycles["viterbi_pl"] * cycle_us, 3),
                    "measured_cycles": hw_cycles["viterbi_pl"],
                    "domain": "FPGA HARDWARE",
                    "status": "LIVE FPGA cycle counter",
                },
                "stage3_block_deint": {
                    "title": "Stage 3 — Block De-Interleaver [FPGA]",
                    "desc": f"{lay['num_cw']} RS codewords | Symbol-level 2D column-in row-out",
                    "codewords": lay["num_cw"],
                    "measured_us": round(hw_cycles["block_pl"] * cycle_us, 3),
                    "measured_cycles": hw_cycles["block_pl"],
                    "domain": "FPGA HARDWARE",
                    "status": "LIVE FPGA cycle counter",
                },
                "stage4_rs_dec": {
                    "title": "Stage 4 — Reed-Solomon RS(101,91) Decoder [FPGA]",
                    "desc": f"Berlekamp-Massey | t=5 | RS corrected={rs_corr} bytes | RS failed={rs_fail} CWs",
                    "hex": format_hex_preview(hw_out),
                    "size_bytes": len(hw_out),
                    "rs_corrections": rs_corr,
                    "rs_fails": rs_fail,
                    "measured_us": round(hw_cycles["rs_pl"] * cycle_us, 3),
                    "measured_cycles": hw_cycles["rs_pl"],
                    "domain": "FPGA HARDWARE",
                    "status": "LIVE FPGA cycle counter",
                },
                "stage5_derand": {
                    "title": "Stage 5 — PRBS De-Randomizer [Zynq PS]",
                    "desc": "x¹⁵+x¹⁴+1 LFSR XOR inverse; executed by uart_bridge on the Zynq ARM",
                    "hex": format_hex_preview(rx5_derand),
                    "recovered_text": recovered_text,
                    "measured_us": round(t_rx5_us, 3),
                    "measured_cycles": hw_cycles["derandomizer_ps"],
                    "domain": "ZYNQ PS",
                },
            },
        }

        self.last_result = result
        return result

    # ──────────────────────────────────────────────────────────────────────
    # FPGA via COM5 UART
    # ──────────────────────────────────────────────────────────────────────
    def _get_serial(self):
        """Open or reuse pyserial connection to COM5."""
        try:
            import serial
        except ImportError:
            return None
        with self._serial_lock:
            if self._serial and self._serial.is_open:
                return self._serial
            try:
                import serial
                s = serial.Serial(
                    port=COM_PORT,
                    baudrate=BAUD_RATE,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=UART_TIMEOUT,
                    write_timeout=5.0,
                )
                s.reset_input_buffer()
                s.reset_output_buffer()
                self._serial = s
                return s
            except Exception:
                return None

    def _close_serial(self):
        with self._serial_lock:
            if self._serial:
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None

    def _run_fpga_uart(self, mode, lay, rx_bits):
        """
        Send encoded bits to FPGA over COM5 and receive all real board stages.
        Protocol (uart_bridge.c):
          TX: MAGIC_TX (4) + mode(1) + n_coded(2LE) + n_out(2LE) +
              n_steps(2LE) + num_cw(2LE) + rs_n(1) + data[n_coded]
          RX: "TRC3" + lengths/counters + eight measured u32 values + buffers
        """
        ser = self._get_serial()
        if ser is None:
            return {"success": False, "error": "Cannot open COM5. Check board power, USB-UART cable, and that no terminal owns the port."}

        n_coded = len(rx_bits)
        n_out   = lay["payload_bytes"]
        n_steps = lay["n_steps"]
        num_cw  = lay["num_cw"]
        rs_n    = lay["rs_n"]
        rate_code = RATE_CODE[lay["rate"]]

        # Build header
        header = (
            MAGIC_TX +
            struct.pack("<B", rate_code) +
            struct.pack("<H", n_coded) +
            struct.pack("<H", n_out) +
            struct.pack("<H", n_steps) +
            struct.pack("<H", num_cw) +
            struct.pack("<B", rs_n)
        )
        # Payload: one byte per bit (0x00 or 0x01)
        data_bytes = bytes(rx_bits)

        try:
            ser.reset_input_buffer()
            ser.write(header + data_bytes)
            ser.flush()

            # Read response magic (4 bytes)
            magic = ser.read(4)
            if len(magic) < 4:
                self._close_serial()
                return {"success": False, "error": "UART timeout: no response from the Zynq firmware."}

            if magic == MAGIC_ERR:
                self._close_serial()
                return {"success": False, "error": "Zynq firmware rejected the frame (decoder version or DMA error)."}

            if magic == MAGIC_RX:
                self._close_serial()
                return {"success": False, "error": "Board is running the old final-output-only firmware. Rebuild and boot the trace firmware."}

            if magic == b'TRC2':
                self._close_serial()
                return {"success": False, "error": "Board is running trace protocol TRC2 without cycle counters. Program the new bitstream and firmware."}

            if magic != MAGIC_RX_TRACE:
                self._close_serial()
                return {"success": False, "error": f"Invalid UART response magic: {magic.hex()}"}

            # Five trace lengths plus RS counters.
            meta = ser.read(14)
            if len(meta) < 14:
                self._close_serial()
                return {"success": False, "error": "UART timeout while reading board trace metadata."}

            helical_len, viterbi_len, block_len, rs_len, final_len, rs_corr, rs_fail = struct.unpack("<HHHHHHH", meta)
            expected_lengths = (n_coded, num_cw * rs_n, num_cw * rs_n, n_out, n_out)
            received_lengths = (helical_len, viterbi_len, block_len, rs_len, final_len)
            if received_lengths != expected_lengths:
                self._close_serial()
                return {
                    "success": False,
                    "error": f"Board trace length mismatch: received {received_lengths}, expected {expected_lengths}.",
                }

            timing_meta = ser.read(32)
            if len(timing_meta) < 32:
                self._close_serial()
                return {"success": False, "error": "UART timeout while reading real board timing counters."}
            (helical_cycles, vit_cycles, block_cycles, rs_cycles,
             pipeline_cycles, derand_cycles, board_cycles,
             pl_clock_hz) = struct.unpack("<IIIIIIII", timing_meta)
            if pl_clock_hz == 0 or not all((helical_cycles, vit_cycles, block_cycles,
                                            rs_cycles, pipeline_cycles, derand_cycles,
                                            board_cycles)):
                self._close_serial()
                return {"success": False, "error": "Board returned an invalid zero performance counter."}

            total_trace_len = sum(received_lengths)
            trace = ser.read(total_trace_len)
            if len(trace) < total_trace_len:
                self._close_serial()
                return {"success": False, "error": f"UART trace short read: received {len(trace)}/{total_trace_len} bytes."}

            offset = 0
            def take(length):
                nonlocal offset
                value = bytes(trace[offset:offset + length])
                offset += length
                return value

            helical_trace = take(helical_len)
            viterbi_trace = take(viterbi_len)
            block_trace = take(block_len)
            rs_trace = take(rs_len)
            payload = take(final_len)

            return {
                "success": True,
                "data": bytes(payload),
                "helical_deinterleaved": helical_trace,
                "viterbi_bytes": viterbi_trace,
                "block_deinterleaved": block_trace,
                "rs_decoded": rs_trace,
                "rs_corr": rs_corr,
                "rs_fail": rs_fail,
                "pl_clock_hz": pl_clock_hz,
                "timing_cycles": {
                    "helical_ps": helical_cycles,
                    "viterbi_pl": vit_cycles,
                    "block_pl": block_cycles,
                    "rs_pl": rs_cycles,
                    "pipeline_pl": pipeline_cycles,
                    "derandomizer_ps": derand_cycles,
                    "board_processing": board_cycles,
                },
            }

        except Exception as e:
            self._close_serial()
            return {"success": False, "error": f"UART transaction failed: {e}"}

    def _hardware_failure(self, mode, input_text, reason):
        """Fail closed: no decoded data or derived metrics without FPGA evidence."""
        return {
            "status": "hardware_unavailable",
            "message": reason,
            "mode": mode,
            "hw_active": False,
            "hw_mode_desc": "NO HARDWARE RESULT — NOTHING WAS DECODED",
            "device": "xc7z010clg400-1",
            "input_text": input_text,
            "recovered_text": "",
            "is_bit_exact": False,
            "metrics_valid": False,
            "timing_us": {},
            "tx_stages": {},
            "rx_stages": {},
        }

    # ──────────────────────────────────────────────────────────────────────
    # BOARD BOOT via XSDB
    # ──────────────────────────────────────────────────────────────────────
    def boot_board(self):
        """Program bitstream + load uart_bridge.elf + start ARM. Returns dict."""
        elf_path = os.path.join(self.base_dir, "sw", "uart_bridge.elf")
        if not os.path.exists(elf_path):
            return {"success": False, "message": "uart_bridge.elf not found. Run: python build_firmware.py"}

        if not os.path.exists(XSDB_PATH):
            return {"success": False, "message": f"xsdb.bat not found at {XSDB_PATH}"}

        try:
            self._close_serial()
            res = subprocess.run(
                [XSDB_PATH, BOOT_TCL],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
                cwd=self.base_dir,
            )
            out = res.stdout + res.stderr
            if "BOOT_OK" in out:
                self.firmware_booted = True
                time.sleep(0.6)   # let UART settle
                return {"success": True, "message": "Firmware booted. COM5 ready.", "log": out}
            elif "ERR_NO_TARGET" in out:
                return {"success": False, "message": "Board not found. Is it powered on?", "log": out}
            else:
                return {"success": False, "message": "Boot failed. Check log.", "log": out}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "XSDB boot timed out (60s)."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_hw_status(self):
        """Quick check: is COM5 open and responding?"""
        ser = self._get_serial()
        if ser is None:
            return {"com_open": False, "hw_active": False, "port": COM_PORT}
        return {
            "com_open": ser.is_open,
            "hw_active": self.hw_connected,
            "firmware_booted": self.firmware_booted,
            "port": COM_PORT,
            "baud": BAUD_RATE,
        }


engine_instance = LDACSEngine()

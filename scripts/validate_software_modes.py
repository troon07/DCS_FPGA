#!/usr/bin/env python3
"""Deterministic end-to-end software check for every supported frame mode."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model.ldacs_ref import (
    MODES,
    TAIL_BITS,
    block_interleave,
    bytes_to_bits,
    conv_encode_punct,
    decode_frame,
    frame_layout,
    helical_interleave,
    randomize,
    rs_encode,
)


def encode_frame(payload: bytes, layout: dict) -> list[int]:
    """Encode one deterministic payload using the same TX path as the console."""
    randomized = randomize(payload)
    rs_k = layout["rs_k"]
    codewords = [
        rs_encode(randomized[index * rs_k:(index + 1) * rs_k])
        for index in range(layout["num_cw"])
    ]
    block_bits = bytes_to_bits(block_interleave(codewords))
    terminated = block_bits + [0] * layout["pad_bits"] + [0] * TAIL_BITS
    return helical_interleave(conv_encode_punct(terminated, layout["rate"]))


def main() -> int:
    failures = 0
    for mode in MODES:
        layout = frame_layout(mode)
        payload = bytes((index * 37 + len(mode)) & 0xFF for index in range(layout["payload_bytes"]))
        encoded = encode_frame(payload, layout)
        decoded = decode_frame(encoded, layout)
        payload_ok = decoded["payload"] == payload
        rs_ok = decoded["n_fail"] == 0
        status = "PASS" if payload_ok and rs_ok else "FAIL"
        print(
            f"{status} {mode}: coded_bits={len(encoded)} "
            f"payload_bytes={len(payload)} rs_corrections={decoded['n_corr']} "
            f"rs_failures={decoded['n_fail']}"
        )
        failures += not (payload_ok and rs_ok)

    print(f"Software validation: {len(MODES) - failures}/{len(MODES)} modes passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

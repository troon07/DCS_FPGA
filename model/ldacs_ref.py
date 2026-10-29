#!/usr/bin/env python3
"""
LDACS coding chain - Python reference model (plays the role of the MATLAB
reference system in Fig. 5 of Kurz et al., IEEE OJIES 2022).

Transmit (encode) chain:
  payload -> randomizer -> Reed-Solomon encoder -> block interleaver
          -> convolutional encoder (+puncturing) -> helical interleaver
Receive (decode) chain (what the ZedBoard implements):
  helical deinterleaver (CPU) -> Viterbi decoder (FPGA) -> block deinterleaver (FPGA)
          -> Reed-Solomon decoder (FPGA) -> derandomizer (CPU)

!!! IMPORTANT !!!
Everything marked "SPEC-CHECK" is a best-effort assumption. The paper does not
list these values. Verify them against the LDACS A/G specification
(Graeupl, Rihacek, Haindl, SESAR2020 PJ14-W2-60, Ed. 00.01.00, 2020) and edit
the constants / functions below (and the matching C / Verilog, see docs/SPEC_CHECK.md).
"""
import argparse, os, random

# ----------------------------------------------------------------------------
# SPEC-CHECK: code parameters
# ----------------------------------------------------------------------------
CONV_G1 = 0o171            # convolutional generator 1 (K = 7)
CONV_G2 = 0o133            # convolutional generator 2
TAIL_BITS = 6              # encoder terminated with K-1 zero bits
# puncturing patterns (X = G1 output, Y = G2 output); per trellis step X is sent before Y
PUNCT = {
    "1/2": ([1], [1]),
    "2/3": ([1, 0], [1, 1]),
    "3/4": ([1, 0, 1], [1, 1, 0]),
}
RATE_CODE = {"1/2": 0, "2/3": 1, "3/4": 2}   # value written to FPGA register

RS_N = 101                 # Reed-Solomon codeword length (bytes)
RS_NSYM = 10               # parity bytes -> corrects up to 5 byte errors
RS_FCR = 0                 # first consecutive root
GF_PRIM = 0x11D            # x^8+x^4+x^3+x^2+1

PRBS_SEED = 0b100101010000000   # randomizer x^15 + x^14 + 1
HELICAL_ROWS = 24               # helical interleaver rows (placeholder)

# Modes from Table 2 of the paper: (modulation, rate, coded bits per block)
MODES = {
    "qpsk_1_2":  ("QPSK", "1/2", 9768),
    "qpsk_2_3":  ("QPSK", "2/3", 9768),
    "qpsk_3_4":  ("QPSK", "3/4", 9768),
    "16qam_1_2": ("16QAM", "1/2", 19536),
    "16qam_2_3": ("16QAM", "2/3", 19536),
    "64qam_1_2": ("64QAM", "1/2", 29304),
    "64qam_2_3": ("64QAM", "2/3", 29304),
    "64qam_3_4": ("64QAM", "3/4", 29304),
}

# ----------------------------------------------------------------------------
# Frame layout (SPEC-CHECK: the spec defines exact per-mode tables)
# ----------------------------------------------------------------------------
def frame_layout(mode):
    _, rate, coded_bits = MODES[mode]
    X, Y = PUNCT[rate]
    P = len(X)
    per_period = sum(X) + sum(Y)
    assert coded_bits % per_period == 0
    n_steps = coded_bits // per_period * P          # trellis steps incl. tail
    data_bits_max = n_steps - TAIL_BITS
    num_cw = data_bits_max // (8 * RS_N)
    pad_bits = data_bits_max - num_cw * 8 * RS_N
    return dict(mode=mode, rate=rate, coded_bits=coded_bits, n_steps=n_steps,
                num_cw=num_cw, pad_bits=pad_bits, rs_n=RS_N, rs_k=RS_N - RS_NSYM,
                payload_bytes=num_cw * (RS_N - RS_NSYM))

# ----------------------------------------------------------------------------
# Randomizer
# ----------------------------------------------------------------------------
def prbs_bits(n, seed=PRBS_SEED):
    reg, out = seed, []
    for _ in range(n):
        fb = ((reg >> 14) ^ (reg >> 13)) & 1
        out.append(fb)
        reg = ((reg << 1) | fb) & 0x7FFF
    return out

def randomize(data):          # the same function de-randomizes (XOR)
    seq = prbs_bits(len(data) * 8)
    out = bytearray()
    for i, b in enumerate(data):
        m = 0
        for k in range(8):
            m = (m << 1) | seq[i * 8 + k]
        out.append(b ^ m)
    return bytes(out)

# ----------------------------------------------------------------------------
# GF(2^8) and Reed-Solomon
# ----------------------------------------------------------------------------
GF_EXP = [0] * 512
GF_LOG = [0] * 256
_x = 1
for _i in range(255):
    GF_EXP[_i] = _x
    GF_LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= GF_PRIM
for _i in range(255, 512):
    GF_EXP[_i] = GF_EXP[_i - 255]

def gf_mul(a, b):
    return 0 if a == 0 or b == 0 else GF_EXP[GF_LOG[a] + GF_LOG[b]]

def gf_inv(a):
    return GF_EXP[255 - GF_LOG[a]]

def _rs_generator():
    g = [1]
    for i in range(RS_NSYM):
        root = GF_EXP[(RS_FCR + i) % 255]
        ng = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            ng[j] ^= c
            ng[j + 1] ^= gf_mul(c, root)
        g = ng
    return g
RS_GEN = _rs_generator()

def rs_encode(msg):
    out = list(msg) + [0] * RS_NSYM
    for i in range(len(msg)):
        c = out[i]
        if c:
            for j in range(1, len(RS_GEN)):
                out[i + j] ^= gf_mul(RS_GEN[j], c)
    return bytes(list(msg) + out[len(msg):])

def rs_decode(r):
    """Returns (data_bytes, n_corrected, ok). Mirrors hw/rtl/rs_dec.v."""
    n, T = len(r), RS_NSYM // 2
    S = []
    for j in range(RS_NSYM):
        a, s = GF_EXP[(RS_FCR + j) % 255], 0
        for b in r:
            s = gf_mul(s, a) ^ b
        S.append(s)
    if not any(S):
        return bytes(r[:n - RS_NSYM]), 0, True
    # Berlekamp-Massey
    Lam = [1] + [0] * RS_NSYM
    B = [1] + [0] * RS_NSYM
    L, m, bb = 0, 1, 1
    for rr in range(RS_NSYM):
        d = S[rr]
        for i in range(1, RS_NSYM + 1):
            if i <= L and i <= rr:
                d ^= gf_mul(Lam[i], S[rr - i])
        if d == 0:
            m += 1
        else:
            coef = gf_mul(d, gf_inv(bb))
            new = [Lam[i] ^ (gf_mul(coef, B[i - m]) if i >= m else 0) for i in range(RS_NSYM + 1)]
            if 2 * L <= rr:
                B, L, bb, m = Lam, rr + 1 - L, d, 1
            else:
                m += 1
            Lam = new
    if L > T:
        return bytes(r[:n - RS_NSYM]), 0, False
    # error evaluator Omega = S*Lambda mod x^NSYM
    Om = []
    for i in range(RS_NSYM):
        v = 0
        for j in range(i + 1):
            v ^= gf_mul(S[i - j], Lam[j])
        Om.append(v)
    # Chien search + Forney
    errs, fail = [], False
    for p in range(n):
        lam_v = odd = 0
        for j in range(RS_NSYM + 1):
            t = gf_mul(Lam[j], GF_EXP[(j * (255 - p)) % 255])
            lam_v ^= t
            if j & 1:
                odd ^= t
        if lam_v == 0:
            om_v = 0
            for i in range(RS_NSYM):
                om_v ^= gf_mul(Om[i], GF_EXP[(i * (255 - p)) % 255])
            f = GF_EXP[(RS_FCR * (255 - p)) % 255]
            if odd == 0 or len(errs) >= T:
                fail = True
            else:
                errs.append((n - 1 - p, gf_mul(gf_mul(f, om_v), gf_inv(odd))))
    if fail or len(errs) != L:
        return bytes(r[:n - RS_NSYM]), 0, False
    out = bytearray(r)
    for pos, val in errs:
        out[pos] ^= val
    return bytes(out[:n - RS_NSYM]), len(errs), True

# ----------------------------------------------------------------------------
# Block (byte) interleaver: round-robin across RS codewords   (SPEC-CHECK)
# ----------------------------------------------------------------------------
def block_interleave(cws):
    d, n = len(cws), len(cws[0])
    return bytes(cws[j % d][j // d] for j in range(d * n))

def block_deinterleave(data, d):
    n = len(data) // d
    return [bytes(data[p * d + i] for p in range(n)) for i in range(d)]

# ----------------------------------------------------------------------------
# Convolutional code + Viterbi (mirrors hw/rtl/viterbi_dec.v)
# ----------------------------------------------------------------------------
def _par(x):
    return bin(x).count("1") & 1

def conv_encode_punct(bits, rate):
    X, Y = PUNCT[rate]
    P, s, out = len(X), 0, []
    for k, u in enumerate(bits):
        reg = (u << 6) | s
        if X[k % P]:
            out.append(_par(reg & CONV_G1))
        if Y[k % P]:
            out.append(_par(reg & CONV_G2))
        s = reg >> 1
    return out

def viterbi_decode(rx, n_steps, rate):
    X, Y = PUNCT[rate]
    P, INIT = len(X), 32
    c1 = [_par(r & CONV_G1) for r in range(128)]
    c2 = [_par(r & CONV_G2) for r in range(128)]
    pm = [0] + [INIT] * 63
    decs, idx = [], 0
    for k in range(n_steps):
        ph = k % P
        r1 = e1 = r2 = e2 = 0
        if X[ph]:
            r1, e1, idx = rx[idx] & 1, 1, idx + 1
        if Y[ph]:
            r2, e2, idx = rx[idx] & 1, 1, idx + 1
        new, dec = [0] * 64, 0
        for ns in range(64):
            reg0, reg1 = ns << 1, (ns << 1) | 1
            m0 = pm[(ns & 31) << 1] + (e1 & (r1 ^ c1[reg0])) + (e2 & (r2 ^ c2[reg0]))
            m1 = pm[((ns & 31) << 1) | 1] + (e1 & (r1 ^ c1[reg1])) + (e2 & (r2 ^ c2[reg1]))
            if m1 < m0:
                new[ns], dec = m1, dec | (1 << ns)
            else:
                new[ns] = m0
        mn = min(new)
        pm = [v - mn for v in new]   # HW uses modulo arithmetic instead; same decisions
        decs.append(dec)
    state, bits = 0, [0] * n_steps
    for k in reversed(range(n_steps)):
        bits[k] = state >> 5
        state = ((state & 31) << 1) | ((decs[k] >> state) & 1)
    return bits

# ----------------------------------------------------------------------------
# Helical interleaver (SPEC-CHECK: placeholder helical-scan permutation)
# out[k] = in[src(k)]
# ----------------------------------------------------------------------------
def helical_src(k, n, rows=HELICAL_ROWS):
    cols = n // rows
    t, r = divmod(k, rows)
    return r * cols + (t + r) % cols

def helical_interleave(bits):
    n = len(bits)
    assert n % HELICAL_ROWS == 0
    return [bits[helical_src(k, n)] for k in range(n)]

def helical_deinterleave(bits):
    n = len(bits)
    out = [0] * n
    for k in range(n):
        out[helical_src(k, n)] = bits[k]
    return out

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def bytes_to_bits(data):
    return [(b >> (7 - i)) & 1 for b in data for i in range(8)]

def bits_to_bytes(bits):
    return bytes(sum(bits[i + k] << (7 - k) for k in range(8)) for i in range(0, len(bits), 8))

def encode_frame(payload, lay):
    rnd = randomize(payload)
    K = lay["rs_k"]
    cws = [rs_encode(rnd[i * K:(i + 1) * K]) for i in range(lay["num_cw"])]
    inter = block_interleave(cws)
    bits = bytes_to_bits(inter) + [0] * lay["pad_bits"] + [0] * TAIL_BITS
    coded = conv_encode_punct(bits, lay["rate"])
    assert len(coded) == lay["coded_bits"]
    return dict(randomized=rnd, rs_in=inter, vit_in=coded, tx=helical_interleave(coded))

def decode_frame(tx_bits, lay):
    vit_in = helical_deinterleave(tx_bits)
    bits = viterbi_decode(vit_in, lay["n_steps"], lay["rate"])
    data = bits_to_bytes(bits[:lay["num_cw"] * lay["rs_n"] * 8])
    deinterleaved = b"".join(block_deinterleave(data, lay["num_cw"]))
    hw_out, n_corr, n_fail = bytearray(), 0, 0
    for offset in range(0, len(deinterleaved), lay["rs_n"]):
        cw = deinterleaved[offset:offset + lay["rs_n"]]
        d, c, ok = rs_decode(cw)
        hw_out += d
        n_corr += c
        n_fail += 0 if ok else 1
    return dict(
        vit_in=vit_in,
        viterbi_bits=bits[:lay["num_cw"] * lay["rs_n"] * 8],
        viterbi_bytes=data,
        block_deinterleaved=deinterleaved,
        hw_out=bytes(hw_out),
        payload=randomize(bytes(hw_out)),
        n_corr=n_corr,
        n_fail=n_fail,
    )

def add_errors(bits, rng, ber=0.0, bursts=0, burst_len=0):
    out = list(bits)
    n = len(out)
    if ber:
        for i in range(n):
            if rng.random() < ber:
                out[i] ^= 1
    for _ in range(bursts):
        s = rng.randrange(0, n - burst_len)
        for i in range(s, s + burst_len):
            out[i] ^= 1
    return out

# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="LDACS reference model / test vector generator")
    ap.add_argument("--mode", default="qpsk_1_2", choices=list(MODES))
    ap.add_argument("--ber", type=float, default=0.0, help="random bit error rate on channel")
    ap.add_argument("--bursts", type=int, default=0, help="number of error bursts")
    ap.add_argument("--burst-len", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=None, help="write test vectors to this directory")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    lay = frame_layout(a.mode)
    payload = bytes(rng.randrange(256) for _ in range(lay["payload_bytes"]))
    enc = encode_frame(payload, lay)
    rx = add_errors(enc["tx"], rng, a.ber, a.bursts, a.burst_len)
    dec = decode_frame(rx, lay)

    nerr_ch = sum(x != y for x, y in zip(rx, enc["tx"]))
    nerr_out = sum(x != y for x, y in zip(dec["payload"], payload))
    print(f"mode={a.mode} layout={lay}")
    print(f"channel bit errors: {nerr_ch}  | RS bytes corrected: {dec['n_corr']}  "
          f"| RS codewords failed: {dec['n_fail']}  | payload byte errors: {nerr_out}")
    print("RESULT:", "PASS (error free)" if nerr_out == 0 else "residual errors")

    if a.out:
        os.makedirs(a.out, exist_ok=True)
        def w(name, data):
            with open(os.path.join(a.out, name), "wb") as f:
                f.write(bytes(data))
        w("tx_bits.bin", rx)                 # input to the C app on the board
        w("vit_in.bin", dec["vit_in"])       # input to FPGA (after helical deint)
        w("hw_expected.bin", dec["hw_out"])  # FPGA output (golden, still randomized)
        w("payload.bin", payload)            # original data
        with open(os.path.join(a.out, "vit_in.mem"), "w") as f:
            f.write("\n".join(f"{b:02x}" for b in dec["vit_in"]) + "\n")
        with open(os.path.join(a.out, "hw_expected.mem"), "w") as f:
            f.write("\n".join(f"{b:02x}" for b in dec["hw_out"]) + "\n")
        with open(os.path.join(a.out, "tb_cfg.vh"), "w") as f:
            f.write(f"localparam CFG_RATE    = {RATE_CODE[lay['rate']]};\n")
            f.write(f"localparam CFG_N_STEPS = {lay['n_steps']};\n")
            f.write(f"localparam CFG_NUM_CW  = {lay['num_cw']};\n")
            f.write(f"localparam CFG_RS_N    = {lay['rs_n']};\n")
            f.write(f"localparam N_IN        = {lay['coded_bits']};\n")
            f.write(f"localparam N_OUT       = {lay['payload_bytes']};\n")
            f.write(f"localparam EXP_CORR    = {dec['n_corr']};\n")
            f.write(f"localparam EXP_FAIL    = {dec['n_fail']};\n")
        print(f"test vectors written to {a.out}")

if __name__ == "__main__":
    main()

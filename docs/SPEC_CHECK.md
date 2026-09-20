# SPEC-CHECK: values you must verify against the LDACS specification

The paper explains the *architecture* but does not list every coding parameter.
This project uses sensible, standard values so the whole chain runs end to end.
Before claiming standard compliance, compare each item with the LDACS A/G
specification (Gräupl, Rihacek, Haindl, SESAR2020 PJ14-W2-60, 2020) and change
it in **every** place listed.

| # | Item | Value used here | Where to change |
|---|------|-----------------|-----------------|
| 1 | Convolutional code | K=7, generators 171/133 (octal), 6 tail bits | `model/ldacs_ref.py`, `hw/rtl/viterbi_dec.v` (the `7'o171`/`7'o133` masks) |
| 2 | Puncturing patterns | 2/3: X=10 Y=11; 3/4: X=101 Y=110 | `model/ldacs_ref.py` `PUNCT`, `viterbi_dec.v` (need_x/need_y block) |
| 3 | Reed–Solomon code | RS(101,91), t=5, GF poly 0x11D, FCR=0 | `model/ldacs_ref.py`, then run `python3 hw/scripts/gen_rs_dec.py`; `sw/include/ldacs.h` |
| 4 | Block interleaver | round-robin bytes across codewords | `model/ldacs_ref.py`, `hw/rtl/block_deint.v` |
| 5 | Helical interleaver | placeholder helical-scan permutation, 24 rows | `model/ldacs_ref.py` `helical_src()`, `sw/src/helical.c` |
| 6 | Randomizer | PRBS x^15+x^14+1, seed 100101010000000 | `model/ldacs_ref.py`, `sw/src/derand.c`, `sw/include/ldacs.h` |
| 7 | Frame layout | codewords/padding derived from coded bits (Table 2) | `model/ldacs_ref.py` `frame_layout()`, `sw/src/modes.c` |

After any change: `./scripts/run_sim.sh` and `cd sw && make host-test` must still pass.
The model, hardware and software are checked against each other, so a
mistake in only one place shows up as a test failure.

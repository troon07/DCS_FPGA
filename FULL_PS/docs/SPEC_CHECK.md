# Shared SPEC-CHECK assumptions

This experiment preserves the original receiver constants. Three-way agreement
and loopback establish implementation consistency, not LDACS standard conformance.
Independent specification-derived vectors remain necessary.

| Item | Value in this experiment | Receiver implementation |
|---|---|---|
| Convolutional code / puncturing | K=7, 171/133 octal, six tails; rates 1/2, 2/3, 3/4 | `sw/src/receiver.c` |
| Reed-Solomon | RS(101,91), ten parity bytes, GF 0x11d, FCR=0 | `sw/src/receiver.c` |
| Byte deinterleaving | Round-robin bytes across codewords | `sw/src/receiver.c` |
| Helical permutation | 24-row helical scan from the baseline | `sw/src/helical.c` |
| PRBS | x^15+x^14+1, seed 0x4a80 | `sw/src/derand.c` |

Encoder, frame layout and complete reference receiver are in `model/ldacs_ref.py`.
Changes must be coordinated across every architecture before rerunning validation.

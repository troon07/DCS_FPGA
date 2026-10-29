/* helical.c - helical deinterleaver (software block, as in the paper)
 * Interleaver: out[k] = in[src(k)]  ->  deinterleaver: out[src(k)] = in[k]
 * SPEC-CHECK: placeholder helical-scan permutation, mirrors model/ldacs_ref.py:helical_src()
 * Implemented with incremental indices (no division in the inner loop). */
#include "ldacs.h"

void helical_deinterleave(const uint8_t *in, uint8_t *out, size_t n)
{
    const size_t rows = LDACS_HELICAL_ROWS;
    const size_t cols = n / rows;
    size_t k = 0;
    for (size_t t = 0; t < cols; t++) {
        for (size_t r = 0; r < rows; r++, k++) {
            size_t c = t + r;
            while (c >= cols) c -= cols;
            out[r * cols + c] = in[k];
        }
    }
}

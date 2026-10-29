/* derand.c - derandomizer, PRBS x^15 + x^14 + 1 (software block, as in the paper)
 * The PRBS sequence is generated once and cached as bytes, so each frame
 * is only a byte-wise XOR (fast on the Cortex-A9).  SPEC-CHECK: polynomial/seed */
#include "ldacs.h"

#define PRBS_CACHE 4096
static uint8_t prbs_bytes[PRBS_CACHE];
static int prbs_ready;

static void prbs_init(void)
{
    uint32_t reg = LDACS_PRBS_SEED;
    for (int i = 0; i < PRBS_CACHE; i++) {
        uint8_t m = 0;
        for (int b = 0; b < 8; b++) {
            uint32_t fb = ((reg >> 14) ^ (reg >> 13)) & 1u;
            m = (uint8_t)((m << 1) | fb);
            reg = ((reg << 1) | fb) & 0x7FFFu;
        }
        prbs_bytes[i] = m;
    }
    prbs_ready = 1;
}

void derandomize(const uint8_t *in, uint8_t *out, size_t nbytes)
{
    if (!prbs_ready) prbs_init();
    for (size_t i = 0; i < nbytes && i < PRBS_CACHE; i++)
        out[i] = in[i] ^ prbs_bytes[i];
}

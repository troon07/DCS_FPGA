/* modes.c - LDACS PHY modes (Table 2 of the paper) and frame layout.
 * Mirrors model/ldacs_ref.py: MODES + frame_layout()  -- SPEC-CHECK */
#include <stdio.h>
#include <string.h>
#include "ldacs.h"

static ldacs_mode_t modes[] = {
    {"qpsk_1_2",  0,  9768}, {"qpsk_2_3",  1,  9768}, {"qpsk_3_4",  2,  9768},
    {"16qam_1_2", 0, 19536}, {"16qam_2_3", 1, 19536},
    {"64qam_1_2", 0, 29304}, {"64qam_2_3", 1, 29304}, {"64qam_3_4", 2, 29304},
};
#define NMODES (int)(sizeof(modes) / sizeof(modes[0]))

static void layout(ldacs_mode_t *m)
{
    static const int period[3]     = {1, 2, 3};   /* trellis steps per puncture period */
    static const int bits_period[3] = {2, 3, 4};  /* coded bits per puncture period   */
    int r = m->rate_code;
    m->n_steps       = m->coded_bits / bits_period[r] * period[r];
    int data_bits    = m->n_steps - LDACS_TAIL_BITS;
    m->num_cw        = data_bits / (8 * LDACS_RS_N);
    m->pad_bits      = data_bits - m->num_cw * 8 * LDACS_RS_N;
    m->rs_k          = LDACS_RS_N - LDACS_RS_NSYM;
    m->payload_bytes = m->num_cw * m->rs_k;
}

const ldacs_mode_t *ldacs_find_mode(const char *name)
{
    for (int i = 0; i < NMODES; i++)
        if (strcmp(modes[i].name, name) == 0) { layout(&modes[i]); return &modes[i]; }
    return NULL;
}

void ldacs_list_modes(void)
{
    for (int i = 0; i < NMODES; i++) {
        layout(&modes[i]);
        printf("  %-10s coded=%5d steps=%5d codewords=%2d payload=%4d bytes\n",
               modes[i].name, modes[i].coded_bits, modes[i].n_steps,
               modes[i].num_cw, modes[i].payload_bytes);
    }
}

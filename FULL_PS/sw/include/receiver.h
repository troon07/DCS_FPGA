#ifndef RECEIVER_H
#define RECEIVER_H
#include <stdint.h>
#define RX_MAX_STEPS 22016
#define RX_MAX_CODED 29304
#define RX_MAX_BYTES 4096
typedef struct {
    unsigned rate, coded, steps, codewords, rs_n, payload;
} rx_config;
/* Caller owns output buffers. Scratch/history are static: one receiver at a time. */
int rx_viterbi(const uint8_t *in, uint8_t *out, const rx_config *cfg);
void rx_block_deinterleave(const uint8_t *in, uint8_t *out, const rx_config *cfg);
int rx_rs_word(const uint8_t *in, uint8_t *out, unsigned n, unsigned *corrected);
void rx_init(void);
#endif

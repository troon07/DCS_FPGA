/* ldacs.h - LDACS decoder software side (runs on the ZedBoard ARM Cortex-A9)
 * Parameters must match model/ldacs_ref.py (see docs/SPEC_CHECK.md). */
#ifndef LDACS_H
#define LDACS_H
#include <stdint.h>
#include <stddef.h>

#define LDACS_TAIL_BITS     6
#define LDACS_RS_N          101
#define LDACS_RS_NSYM       10
#define LDACS_HELICAL_ROWS  24          /* SPEC-CHECK */
#define LDACS_PRBS_SEED     0x4A80      /* 0b100101010000000, SPEC-CHECK */

typedef struct {
    const char *name;
    int rate_code;        /* 0 = 1/2, 1 = 2/3, 2 = 3/4 */
    int coded_bits;
    /* derived by ldacs_layout() */
    int n_steps, num_cw, pad_bits, rs_k, payload_bytes;
} ldacs_mode_t;

const ldacs_mode_t *ldacs_find_mode(const char *name);
void ldacs_list_modes(void);

/* helical.c : helical deinterleaver (SW block #1) */
void helical_deinterleave(const uint8_t *in, uint8_t *out, size_t n);

/* derand.c  : derandomizer (SW block #5), in-place allowed */
void derandomize(const uint8_t *in, uint8_t *out, size_t nbytes);

/* ldacs_hw.c : FPGA access via /dev/mem + u-dma-buf */
typedef struct {
    int      mem_fd;
    uint32_t *dma;           /* AXI DMA registers        */
    uint32_t *dec;           /* decoder AXI-Lite registers */
    int      tx_fd, rx_fd;
    uint8_t  *tx_buf, *rx_buf;
    uint64_t tx_phys, rx_phys;
    size_t   buf_size;
} ldacs_hw_t;

int  hw_open(ldacs_hw_t *hw, uint32_t dma_base, uint32_t dec_base);
void hw_close(ldacs_hw_t *hw);
void hw_configure(ldacs_hw_t *hw, const ldacs_mode_t *m);
int  hw_decode(ldacs_hw_t *hw, size_t in_len, size_t out_len, int timeout_ms);
void hw_read_stats(ldacs_hw_t *hw, uint32_t *frames, uint32_t *corr, uint32_t *fail);

/* decoder register offsets */
#define DEC_CTRL     0x00
#define DEC_STATUS   0x04
#define DEC_RATE     0x08
#define DEC_N_STEPS  0x0C
#define DEC_NUM_CW   0x10
#define DEC_RS_N     0x14
#define DEC_FRAMES   0x18
#define DEC_RS_CORR  0x1C
#define DEC_RS_FAIL  0x20
#define DEC_VERSION  0x24
#endif

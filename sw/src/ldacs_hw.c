/* ldacs_hw.c - talks to the FPGA from Linux user space
 *
 * Data path : AXI DMA in "direct register mode" (no scatter-gather)
 * Buffers   : two u-dma-buf contiguous buffers, allocated ONCE at start
 *             (tip: no per-transfer allocation, zero-copy via mmap)
 * Completion: polling of the DMA status register (tip: no interrupt overhead)
 * Registers : /dev/mem mmap (needs root). Addresses come from Vivado's Address Editor.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include "ldacs.h"

/* AXI DMA register offsets (PG021) */
#define MM2S_DMACR  0x00
#define MM2S_DMASR  0x04
#define MM2S_SA     0x18
#define MM2S_LENGTH 0x28
#define S2MM_DMACR  0x30
#define S2MM_DMASR  0x34
#define S2MM_DA     0x48
#define S2MM_LENGTH 0x58
#define DMACR_RS    (1u << 0)
#define DMACR_RESET (1u << 2)
#define DMASR_HALT  (1u << 0)
#define DMASR_IDLE  (1u << 1)
#define DMASR_IOC   (1u << 12)
#define DMASR_ERR   (1u << 14)
#define DMASR_ERRS  0x770u

#define MAP_LEN 0x10000

static inline void wr(uint32_t *b, uint32_t off, uint32_t v) { b[off >> 2] = v; }
static inline uint32_t rd(uint32_t *b, uint32_t off) { return b[off >> 2]; }

static int read_sysfs_u64(const char *path, uint64_t *v)
{
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    int ok = fscanf(f, "%llx", (unsigned long long *)v) == 1;
    fclose(f);
    return ok ? 0 : -1;
}

static int open_udmabuf(const char *name, int *fd, uint8_t **buf, uint64_t *phys, size_t *size)
{
    char path[128];
    uint64_t sz;
    snprintf(path, sizeof(path), "/sys/class/u-dma-buf/%s/phys_addr", name);
    if (read_sysfs_u64(path, phys)) { fprintf(stderr, "cannot read %s (is u-dma-buf loaded?)\n", path); return -1; }
    snprintf(path, sizeof(path), "/sys/class/u-dma-buf/%s/size", name);
    FILE *f = fopen(path, "r");
    if (!f || fscanf(f, "%llu", (unsigned long long *)&sz) != 1) { if (f) fclose(f); return -1; }
    fclose(f);
    snprintf(path, sizeof(path), "/dev/%s", name);
    *fd = open(path, O_RDWR | O_SYNC);   /* O_SYNC: cache disabled, DMA sees the data */
    if (*fd < 0) { perror(path); return -1; }
    *buf = mmap(NULL, sz, PROT_READ | PROT_WRITE, MAP_SHARED, *fd, 0);
    if (*buf == MAP_FAILED) { perror("mmap udmabuf"); return -1; }
    *size = (size_t)sz;
    return 0;
}

static void dma_reset(uint32_t *dma)
{
    wr(dma, MM2S_DMACR, DMACR_RESET);
    wr(dma, S2MM_DMACR, DMACR_RESET);
    for (int i = 0; i < 1000 && (rd(dma, MM2S_DMACR) & DMACR_RESET); i++) usleep(100);
    wr(dma, MM2S_DMASR, 0xFFFFFFFF);
    wr(dma, S2MM_DMASR, 0xFFFFFFFF);
}

int hw_open(ldacs_hw_t *hw, uint32_t dma_base, uint32_t dec_base)
{
    memset(hw, 0, sizeof(*hw));
    hw->mem_fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (hw->mem_fd < 0) { perror("/dev/mem (run as root)"); return -1; }
    hw->dma = mmap(NULL, MAP_LEN, PROT_READ | PROT_WRITE, MAP_SHARED, hw->mem_fd, dma_base);
    hw->dec = mmap(NULL, MAP_LEN, PROT_READ | PROT_WRITE, MAP_SHARED, hw->mem_fd, dec_base);
    if (hw->dma == MAP_FAILED || hw->dec == MAP_FAILED) { perror("mmap registers"); return -1; }

    size_t tx_size, rx_size;
    if (open_udmabuf("udmabuf_tx", &hw->tx_fd, &hw->tx_buf, &hw->tx_phys, &tx_size)) return -1;
    if (open_udmabuf("udmabuf_rx", &hw->rx_fd, &hw->rx_buf, &hw->rx_phys, &rx_size)) return -1;
    hw->buf_size = tx_size < rx_size ? tx_size : rx_size;

    uint32_t ver = rd(hw->dec, DEC_VERSION);
    if (ver != 0x4C444331) {
        fprintf(stderr, "decoder VERSION register = 0x%08x (expected 0x4C444331). Wrong address or bitstream?\n", ver);
        return -1;
    }
    dma_reset(hw->dma);
    wr(hw->dec, DEC_CTRL, 0x3);             /* soft reset + clear counters */
    return 0;
}

void hw_close(ldacs_hw_t *hw)
{
    if (hw->tx_buf) munmap(hw->tx_buf, hw->buf_size);
    if (hw->rx_buf) munmap(hw->rx_buf, hw->buf_size);
    if (hw->dma) munmap(hw->dma, MAP_LEN);
    if (hw->dec) munmap(hw->dec, MAP_LEN);
    if (hw->tx_fd > 0) close(hw->tx_fd);
    if (hw->rx_fd > 0) close(hw->rx_fd);
    if (hw->mem_fd > 0) close(hw->mem_fd);
}

void hw_configure(ldacs_hw_t *hw, const ldacs_mode_t *m)
{
    wr(hw->dec, DEC_RATE,    (uint32_t)m->rate_code);
    wr(hw->dec, DEC_N_STEPS, (uint32_t)m->n_steps);
    wr(hw->dec, DEC_NUM_CW,  (uint32_t)m->num_cw);
    wr(hw->dec, DEC_RS_N,    LDACS_RS_N);
    /* keep both DMA channels running; only address + length are written per frame */
    wr(hw->dma, MM2S_DMACR, DMACR_RS);
    wr(hw->dma, S2MM_DMACR, DMACR_RS);
    wr(hw->dma, MM2S_SA, (uint32_t)hw->tx_phys);
    wr(hw->dma, S2MM_DA, (uint32_t)hw->rx_phys);
}

/* Input must already be in hw->tx_buf. Result appears in hw->rx_buf.
 * Returns number of bytes received, or -1. */
int hw_decode(ldacs_hw_t *hw, size_t in_len, size_t out_len, int timeout_ms)
{
    uint32_t *d = hw->dma;
    wr(d, MM2S_DMASR, DMASR_IOC);
    wr(d, S2MM_DMASR, DMASR_IOC);
    wr(d, S2MM_DA, (uint32_t)hw->rx_phys);
    wr(d, S2MM_LENGTH, (uint32_t)out_len);   /* arm receiver first */
    wr(d, MM2S_SA, (uint32_t)hw->tx_phys);
    wr(d, MM2S_LENGTH, (uint32_t)in_len);    /* this starts the transfer */

    struct timespec t0, t;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (;;) {
        uint32_t sr = rd(d, S2MM_DMASR);
        if (sr & DMASR_IOC) break;
        if ((sr | rd(d, MM2S_DMASR)) & DMASR_ERRS) {
            fprintf(stderr, "DMA error: MM2S_SR=0x%08x S2MM_SR=0x%08x\n", rd(d, MM2S_DMASR), sr);
            return -1;
        }
        clock_gettime(CLOCK_MONOTONIC, &t);
        if ((t.tv_sec - t0.tv_sec) * 1000 + (t.tv_nsec - t0.tv_nsec) / 1000000 > timeout_ms) {
            fprintf(stderr, "timeout: MM2S_SR=0x%08x S2MM_SR=0x%08x DEC_STATUS=0x%x\n",
                    rd(d, MM2S_DMASR), sr, rd(hw->dec, DEC_STATUS));
            return -1;
        }
    }
    return (int)rd(d, S2MM_LENGTH);
}

void hw_read_stats(ldacs_hw_t *hw, uint32_t *frames, uint32_t *corr, uint32_t *fail)
{
    *frames = rd(hw->dec, DEC_FRAMES);
    *corr   = rd(hw->dec, DEC_RS_CORR);
    *fail   = rd(hw->dec, DEC_RS_FAIL);
}

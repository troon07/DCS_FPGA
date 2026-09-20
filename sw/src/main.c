/* main.c - LDACS HW/SW co-design decoder demo for the ZedBoard
 *
 *   tx_bits.bin --(SW) helical deinterleaver--> FPGA [Viterbi -> block deint -> RS]
 *               --(SW) derandomizer--> compare with payload.bin
 *
 * Prints per-block processing times like Table 3 of the paper.
 *
 * Usage (as root on the board):
 *   ./ldacs_decode -m qpsk_1_2 -d tv/qpsk_1_2 [-n 100] [--dma 0x40400000] [--dec 0x43C00000]
 */
#define _GNU_SOURCE
#include <getopt.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include "ldacs.h"

static double now_us(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e6 + t.tv_nsec / 1e3;
}

static uint8_t *load(const char *dir, const char *name, size_t *len)
{
    char path[512];
    snprintf(path, sizeof(path), "%s/%s", dir, name);
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); exit(1); }
    fseek(f, 0, SEEK_END);
    *len = (size_t)ftell(f);
    rewind(f);
    uint8_t *buf = malloc(*len);
    if (fread(buf, 1, *len, f) != *len) { perror("read"); exit(1); }
    fclose(f);
    return buf;
}

static void usage(void)
{
    printf("usage: ldacs_decode -m <mode> -d <test-vector-dir> [-n iterations] [-c cpu]\n"
           "                    [--dma <addr>] [--dec <addr>]\n"
           "modes:\n");
    ldacs_list_modes();
}

int main(int argc, char **argv)
{
    const char *mode_name = "qpsk_1_2", *dir = ".";
    int iters = 100, cpu = 1;
    uint32_t dma_base = 0x40400000, dec_base = 0x43C00000;   /* check Vivado Address Editor */
    static struct option lo[] = {{"dma", 1, 0, 'A'}, {"dec", 1, 0, 'B'}, {"help", 0, 0, 'h'}, {0, 0, 0, 0}};
    int o;
    while ((o = getopt_long(argc, argv, "m:d:n:c:h", lo, NULL)) != -1) {
        switch (o) {
        case 'm': mode_name = optarg; break;
        case 'd': dir = optarg; break;
        case 'n': iters = atoi(optarg); break;
        case 'c': cpu = atoi(optarg); break;
        case 'A': dma_base = (uint32_t)strtoul(optarg, NULL, 0); break;
        case 'B': dec_base = (uint32_t)strtoul(optarg, NULL, 0); break;
        default: usage(); return 0;
        }
    }
    const ldacs_mode_t *m = ldacs_find_mode(mode_name);
    if (!m) { usage(); return 1; }

    /* tip: pin to one core, real-time priority, lock memory */
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    if (sched_setaffinity(0, sizeof(set), &set)) perror("sched_setaffinity (continuing)");
    struct sched_param sp = {.sched_priority = 80};
    if (sched_setscheduler(0, SCHED_FIFO, &sp)) perror("SCHED_FIFO (continuing)");
    mlockall(MCL_CURRENT | MCL_FUTURE);

    size_t tx_len, exp_len;
    uint8_t *tx_bits = load(dir, "tx_bits.bin", &tx_len);
    uint8_t *payload = load(dir, "payload.bin", &exp_len);
    if ((int)tx_len != m->coded_bits || (int)exp_len != m->payload_bytes) {
        fprintf(stderr, "test vector size mismatch for mode %s (got %zu/%zu, expected %d/%d)\n",
                m->name, tx_len, exp_len, m->coded_bits, m->payload_bytes);
        return 1;
    }
    uint8_t *out = malloc(exp_len);

    ldacs_hw_t hw;
    if (hw_open(&hw, dma_base, dec_base)) return 1;
    if (hw.buf_size < tx_len) { fprintf(stderr, "u-dma-buf too small\n"); return 1; }
    hw_configure(&hw, m);

    double t_hel = 0, t_hw = 0, t_der = 0, t_tot = 0, worst = 0;
    int bad_frames = 0;
    for (int it = 0; it < iters; it++) {
        double a = now_us();
        helical_deinterleave(tx_bits, hw.tx_buf, tx_len);      /* writes straight into DMA buffer */
        double b = now_us();
        int got = hw_decode(&hw, tx_len, exp_len, 1000);
        double c = now_us();
        if (got != (int)exp_len) { fprintf(stderr, "frame %d: received %d bytes\n", it, got); return 1; }
        derandomize(hw.rx_buf, out, exp_len);
        double d = now_us();
        if (memcmp(out, payload, exp_len)) bad_frames++;
        t_hel += b - a; t_hw += c - b; t_der += d - c; t_tot += d - a;
        if (d - a > worst) worst = d - a;
    }

    uint32_t frames, corr, fail;
    hw_read_stats(&hw, &frames, &corr, &fail);
    double avg = t_tot / iters;
    double mbps = (m->payload_bytes * 8.0) / (avg / 1e6) / 1e6;

    printf("\nLDACS HW/SW decoder - mode %s, %d frames\n", m->name, iters);
    printf("---------------------------------------------------------\n");
    printf(" Decoding unit                        avg time [us]\n");
    printf(" Helical deinterleaver (SW)           %10.2f\n", t_hel / iters);
    printf(" FPGA: DMA + Viterbi + deint + RS     %10.2f\n", t_hw / iters);
    printf(" Derandomizer (SW)                    %10.2f\n", t_der / iters);
    printf(" Total per data block                 %10.2f   (worst %.2f)\n", avg, worst);
    printf("---------------------------------------------------------\n");
    printf(" Payload throughput                   %10.3f Mb/s\n", mbps);
    printf(" FPGA frames=%u  RS bytes corrected=%u  RS failed codewords=%u\n", frames, corr, fail);
    printf(" Frames with payload errors: %d / %d  -> %s\n", bad_frames, iters,
           bad_frames ? "residual errors (expected only for very noisy vectors)" : "ALL CORRECT");

    hw_close(&hw);
    free(tx_bits); free(payload); free(out);
    return bad_frames ? 2 : 0;
}

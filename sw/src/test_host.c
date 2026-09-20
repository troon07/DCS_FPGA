/* test_host.c - checks the software blocks on a PC (no FPGA needed)
 * Compares helical_deinterleave() and derandomize() with the Python model output. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ldacs.h"

static uint8_t *load(const char *dir, const char *name, size_t *len)
{
    char path[512];
    snprintf(path, sizeof(path), "%s/%s", dir, name);
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); exit(1); }
    fseek(f, 0, SEEK_END); *len = (size_t)ftell(f); rewind(f);
    uint8_t *b = malloc(*len);
    if (fread(b, 1, *len, f) != *len) exit(1);
    fclose(f);
    return b;
}

int main(int argc, char **argv)
{
    if (argc < 3) { printf("usage: test_host <mode> <vector-dir>\n"); return 1; }
    const ldacs_mode_t *m = ldacs_find_mode(argv[1]);
    if (!m) { ldacs_list_modes(); return 1; }
    size_t n_tx, n_vit, n_hw, n_pl;
    uint8_t *tx = load(argv[2], "tx_bits.bin", &n_tx);
    uint8_t *vit = load(argv[2], "vit_in.bin", &n_vit);
    uint8_t *hw = load(argv[2], "hw_expected.bin", &n_hw);
    uint8_t *pl = load(argv[2], "payload.bin", &n_pl);
    int fails = 0;

    if ((int)n_tx != m->coded_bits || (int)n_pl != m->payload_bytes) {
        printf("FAIL: layout mismatch between C and Python\n"); return 1;
    }
    uint8_t *tmp = malloc(n_tx);
    helical_deinterleave(tx, tmp, n_tx);
    int ok = memcmp(tmp, vit, n_tx) == 0;
    printf("helical deinterleaver : %s\n", ok ? "PASS" : "FAIL"); fails += !ok;

    uint8_t *out = malloc(n_hw);
    derandomize(hw, out, n_hw);
    ok = memcmp(out, pl, n_pl) == 0;
    printf("derandomizer          : %s%s\n", ok ? "PASS" : "FAIL",
           ok ? "" : " (only valid for vectors that decode error free)");
    fails += !ok;
    return fails;
}

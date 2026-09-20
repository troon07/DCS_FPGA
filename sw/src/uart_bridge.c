/* uart_bridge.c - Bare-metal LDACS UART bridge firmware for Zynq PS ARM
 *
 * Runs standalone on the Zynq ARM Cortex-A9 (loaded via XSDB dow + con).
 * NO OS, NO Linux – direct register access only.
 *
 * Protocol over UART (115200 8N1):
 *   PC -> FPGA:
 *     [4 bytes] magic   = 0xLDAC (0x4C 0x44 0x41 0x43)
 *     [1 byte]  mode    : 0=qpsk_1_2  1=qpsk_2_3  2=qpsk_3_4
 *     [2 bytes] n_coded : coded_bits (little-endian)
 *     [2 bytes] n_out   : payload_bytes (little-endian)
 *     [2 bytes] n_steps : trellis steps (little-endian)
 *     [2 bytes] num_cw  : RS codewords (little-endian)
 *     [1 byte]  rs_n    : RS N (101)
 *     [n_coded bytes] raw encoded bits (0x00 or 0x01 per byte)
 *
 *   FPGA -> PC:
 *     [4 bytes] magic   = 0xACLD (0x41 0x43 0x4C 0x44)
 *     [2 bytes] n_out   : actual bytes returned
 *     [2 bytes] rs_corr : RS corrections
 *     [2 bytes] rs_fail : RS failures
 *     [n_out bytes] decoded payload bytes
 *
 * Memory map (from Vivado address editor, confirmed via XSDB):
 *   AXI DMA base    : 0x40400000
 *   LDACS Decoder   : 0x40000000
 *   DMA TX buffer   : 0x00100000  (1MB into DDR, safe for bare-metal)
 *   DMA RX buffer   : 0x00200000  (2MB into DDR)
 *   PS UART0 base   : 0xE0000000  (selected by the EDGE Z7-10 Vivado preset)
 */

#include <stdint.h>
#include "ldacs.h"

extern uint32_t __bss_start, __bss_end, __stack_top;

void bridge_main(void) __attribute__((noreturn));

/* Entry point used by XSDB.  Establish a known C runtime before any UART,
 * PRBS cache, or DMA-buffer state is touched. */
void _start(void) __attribute__((naked, noreturn));
void _start(void)
{
    __asm volatile (
        "ldr sp, =__stack_top\n"
        "ldr r0, =__bss_start\n"
        "ldr r1, =__bss_end\n"
        "mov r2, #0\n"
        "1: cmp r0, r1\n"
        "bcs 2f\n"
        "str r2, [r0], #4\n"
        "b 1b\n"
        "2: b bridge_main\n"
    );
}

/* Use uncached DDR accesses for the bare-metal DMA buffers.  This avoids
 * stale MM2S reads and stale S2MM results until cache-maintenance support is
 * deliberately added. */
static void disable_caches(void)
{
    uint32_t sctlr;
    __asm volatile ("mrc p15, 0, %0, c1, c0, 0" : "=r"(sctlr));
    sctlr &= ~((1u << 2) | (1u << 12));
    __asm volatile ("mcr p15, 0, %0, c1, c0, 0\n\tdsb\n\tisb"
                     :: "r"(sctlr) : "memory");
}

/* -----------------------------------------------------------------------
 * Memory-mapped register helpers
 * --------------------------------------------------------------------- */
static inline void     wreg(uint32_t addr, uint32_t val) { *(volatile uint32_t *)addr = val; }
static inline uint32_t rreg(uint32_t addr)               { return *(volatile uint32_t *)addr; }
static inline void     wreg8(uint32_t addr, uint8_t val) { *(volatile uint8_t  *)addr = val; }
static inline uint8_t  rreg8(uint32_t addr)              { return *(volatile uint8_t  *)addr; }

/* -----------------------------------------------------------------------
 * PS UART0 registers (EDGE Z7-10 board preset: UART0 -> MIO 14/15)
 * --------------------------------------------------------------------- */
#define UART_BASE       0xE0000000UL
#define UART_CR         (UART_BASE + 0x00)   /* Control            */
#define UART_MR         (UART_BASE + 0x04)   /* Mode               */
#define UART_SR         (UART_BASE + 0x2C)   /* Status             */
#define UART_FIFO       (UART_BASE + 0x30)   /* TX/RX FIFO         */
#define UART_BAUDGEN    (UART_BASE + 0x18)   /* Baud Rate Gen      */
#define UART_BAUDDIV    (UART_BASE + 0x34)   /* Baud Rate Divider  */

/* Status bits */
#define UART_SR_TXFULL  (1u << 4)
#define UART_SR_RXEMPTY (1u << 1)
#define UART_SR_TXEMPTY (1u << 3)

/* -----------------------------------------------------------------------
 * AXI DMA register offsets (PG021)
 * --------------------------------------------------------------------- */
#define DMA_BASE        0x40400000UL
#define MM2S_DMACR      0x00
#define MM2S_DMASR      0x04
#define MM2S_SA         0x18
#define MM2S_LENGTH     0x28
#define S2MM_DMACR      0x30
#define S2MM_DMASR      0x34
#define S2MM_DA         0x48
#define S2MM_LENGTH     0x58
#define DMACR_RS        (1u << 0)
#define DMACR_RESET     (1u << 2)
#define DMASR_IOC       (1u << 12)
#define DMASR_ERRS      0x00000770u

/* -----------------------------------------------------------------------
 * LDACS Decoder AXI-Lite register offsets
 * --------------------------------------------------------------------- */
#define DEC_BASE        0x40000000UL
#define DEC_CTRL        0x00
#define DEC_STATUS      0x04
#define DEC_RATE        0x08
#define DEC_N_STEPS     0x0C
#define DEC_NUM_CW      0x10
#define DEC_RS_N        0x14
#define DEC_FRAMES      0x18
#define DEC_RS_CORR     0x1C
#define DEC_RS_FAIL     0x20
#define DEC_VERSION     0x24

/* -----------------------------------------------------------------------
 * DMA buffers in DDR (1 MB-aligned, safe for bare-metal without MMU)
 * TX: 0x00100000  (enough for 64K bits = 65536 bytes – biggest LDACS frame)
 * RX: 0x00200000  (enough for 1024 payload bytes)
 * --------------------------------------------------------------------- */
#define DMA_TX_PHYS     0x00100000UL
#define DMA_RX_PHYS     0x00200000UL
#define TX_BUF_MAX      65536
#define RX_BUF_MAX      4096

static volatile uint8_t *tx_buf = (volatile uint8_t *)DMA_TX_PHYS;
static volatile uint8_t *rx_buf = (volatile uint8_t *)DMA_RX_PHYS;
static uint8_t helical_buf[TX_BUF_MAX];

/* -----------------------------------------------------------------------
 * UART helpers
 * --------------------------------------------------------------------- */
static void uart_init_115200(void)
{
    /* Disable TX/RX, reset */
    wreg(UART_CR, 0x28);          /* TXDIS | RXDIS */
    /* 8N1, normal mode */
    wreg(UART_MR, 0x0020);        /* 8 bits, no parity, 1 stop */
    /* 115200 baud from 100 MHz UART_REF_CLK:
     *   BAUD_RATE_GEN  = 62  (BDIV+1 prescaler)
     *   BAUD_RATE_DIV  = 6   → 100e6 / (62*(6+1)) = 230769 → hmm
     *   Use: BDIV=6, CD=124 → 100e6/(124*7) = 115207 ≈ 115200 */
    wreg(UART_BAUDDIV, 6);        /* BDIV = 6  (divisor = BDIV+1 = 7) */
    wreg(UART_BAUDGEN, 124);      /* CD   = 124 */
    /* Enable TX + RX, clear FIFOs */
    wreg(UART_CR, 0x17);          /* RXEN | TXEN | RXRES | TXRES */
}

static void uart_putc(uint8_t c)
{
    while (rreg(UART_SR) & UART_SR_TXFULL) {}
    wreg(UART_FIFO, c);
}

static uint8_t uart_getc(void)
{
    while (rreg(UART_SR) & UART_SR_RXEMPTY) {}
    return (uint8_t)(rreg(UART_FIFO) & 0xFF);
}

static void uart_put_u16(uint16_t v)
{
    uart_putc((uint8_t)(v & 0xFF));
    uart_putc((uint8_t)(v >> 8));
}

static uint16_t uart_get_u16(void)
{
    uint8_t lo = uart_getc();
    uint8_t hi = uart_getc();
    return (uint16_t)(lo | (hi << 8));
}

static void uart_write_buf(const volatile uint8_t *buf, uint32_t len)
{
    for (uint32_t i = 0; i < len; i++)
        uart_putc(buf[i]);
    /* Flush TX FIFO */
    while (!(rreg(UART_SR) & UART_SR_TXEMPTY)) {}
}

static void uart_read_buf(volatile uint8_t *buf, uint32_t len)
{
    for (uint32_t i = 0; i < len; i++)
        buf[i] = uart_getc();
}

/* -----------------------------------------------------------------------
 * AXI DMA helpers
 * --------------------------------------------------------------------- */
static void dma_reset(void)
{
    wreg(DMA_BASE + MM2S_DMACR, DMACR_RESET);
    wreg(DMA_BASE + S2MM_DMACR, DMACR_RESET);
    volatile int i = 0;
    while (i < 100000 && (rreg(DMA_BASE + MM2S_DMACR) & DMACR_RESET)) i++;
    wreg(DMA_BASE + MM2S_DMASR, 0xFFFFFFFF);
    wreg(DMA_BASE + S2MM_DMASR, 0xFFFFFFFF);
}

static int dma_transfer(uint32_t tx_phys, uint32_t tx_len,
                        uint32_t rx_phys, uint32_t rx_len)
{
    /* Arm S2MM first (receiver), then start MM2S (transmitter) */
    wreg(DMA_BASE + MM2S_DMASR, DMASR_IOC);
    wreg(DMA_BASE + S2MM_DMASR, DMASR_IOC);

    wreg(DMA_BASE + MM2S_DMACR, DMACR_RS);
    wreg(DMA_BASE + S2MM_DMACR, DMACR_RS);

    wreg(DMA_BASE + S2MM_DA,     rx_phys);
    wreg(DMA_BASE + S2MM_LENGTH, rx_len);      /* arm receiver */

    wreg(DMA_BASE + MM2S_SA,     tx_phys);
    wreg(DMA_BASE + MM2S_LENGTH, tx_len);      /* start transfer */

    /* Poll for completion (timeout ~1 second at ~500 MHz) */
    volatile uint32_t count = 0;
    for (count = 0; count < 50000000u; count++) {
        uint32_t sr = rreg(DMA_BASE + S2MM_DMASR);
        if (sr & DMASR_IOC) return 0;   /* done */
        if ((sr | rreg(DMA_BASE + MM2S_DMASR)) & DMASR_ERRS) return -1; /* error */
    }
    return -2;  /* timeout */
}

/* -----------------------------------------------------------------------
 * Send error response to PC
 * --------------------------------------------------------------------- */
static void send_error(void)
{
    /* magic ERR */
    uart_putc(0xFF); uart_putc(0xFF); uart_putc(0xFF); uart_putc(0xFF);
}

/* -----------------------------------------------------------------------
 * Main loop
 * --------------------------------------------------------------------- */
void bridge_main(void)
{
    disable_caches();
    /* Initialize UART */
    uart_init_115200();

    /* Unlock SLCR */
    wreg(0xF8000008, 0xDF0D);
    /* Enable PL clock + level shifters */
    wreg(0xF8000900, 0x0F);
    wreg(0xF8000240, 0x00);

    /* Verify decoder version */
    uint32_t ver = rreg(DEC_BASE + DEC_VERSION);
    if (ver != 0x4C444331) {
        /* Wrong bitstream - keep sending ERR until watchdog or reset */
        for (;;) send_error();
    }

    /* Reset decoder */
    wreg(DEC_BASE + DEC_CTRL, 0x3);
    volatile int d = 0; for (d = 0; d < 1000; d++);
    wreg(DEC_BASE + DEC_CTRL, 0x0);

    /* Main command loop */
    for (;;) {
        /* Wait for magic header: 0x4C 0x44 0x41 0x43 ("LDAC") */
        uint8_t magic[4];
        magic[0] = uart_getc();
        if (magic[0] != 0x4C) continue;
        magic[1] = uart_getc();
        if (magic[1] != 0x44) continue;
        magic[2] = uart_getc();
        if (magic[2] != 0x41) continue;
        magic[3] = uart_getc();
        if (magic[3] != 0x43) continue;

        /* Read frame parameters */
        uint8_t  mode    = uart_getc();
        uint16_t n_coded = uart_get_u16();
        uint16_t n_out   = uart_get_u16();
        uint16_t n_steps = uart_get_u16();
        uint16_t num_cw  = uart_get_u16();
        uint8_t  rs_n    = uart_getc();

        /* Bounds check */
        if (n_coded > TX_BUF_MAX || n_out > RX_BUF_MAX || n_coded == 0 || n_out == 0 ||
            (n_coded % LDACS_HELICAL_ROWS) != 0) {
            send_error();
            continue;
        }

        /* PS stage 1: receive helical-interleaved bits, then deinterleave
         * into the DMA source buffer. */
        uart_read_buf(helical_buf, n_coded);
        helical_deinterleave(helical_buf, (uint8_t *)tx_buf, n_coded);

        /* Configure LDACS decoder */
        wreg(DEC_BASE + DEC_CTRL,    0x3);   /* reset + clear stats */
        volatile int r = 0; for (r = 0; r < 1000; r++);
        wreg(DEC_BASE + DEC_CTRL,    0x0);
        wreg(DEC_BASE + DEC_RATE,    (uint32_t)mode);
        wreg(DEC_BASE + DEC_N_STEPS, (uint32_t)n_steps);
        wreg(DEC_BASE + DEC_NUM_CW,  (uint32_t)num_cw);
        wreg(DEC_BASE + DEC_RS_N,    (uint32_t)rs_n);

        /* Reset DMA */
        dma_reset();

        /* Run DMA: TX buf -> decoder -> RX buf */
        int ret = dma_transfer(DMA_TX_PHYS, (uint32_t)n_coded,
                               DMA_RX_PHYS, (uint32_t)n_out);

        if (ret != 0) {
            send_error();
            continue;
        }

        /* Read stats */
        uint16_t rs_corr = (uint16_t)(rreg(DEC_BASE + DEC_RS_CORR) & 0xFFFF);
        uint16_t rs_fail = (uint16_t)(rreg(DEC_BASE + DEC_RS_FAIL) & 0xFFFF);

        /* PS stage 5: derandomize the FPGA's randomized payload in place. */
        derandomize((const uint8_t *)rx_buf, (uint8_t *)rx_buf, n_out);

        /* Send response: magic "ACLD" + n_out + rs_corr + rs_fail + payload */
        uart_putc(0x41); uart_putc(0x43); uart_putc(0x4C); uart_putc(0x44);
        uart_put_u16(n_out);
        uart_put_u16(rs_corr);
        uart_put_u16(rs_fail);
        uart_write_buf(rx_buf, n_out);
    }
}

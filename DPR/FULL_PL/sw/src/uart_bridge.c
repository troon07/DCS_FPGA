/* Research receiver transport. ARCH=0 hybrid, 1 FULL_PL, 2 FULL_PS.
 * Algorithms are assigned by ARCH; UART/control are always ARM transport.
 * LDAC trace protocol is retained. LDB1 benchmarks ONE decode per iteration.
 * Same no-cache policy on all variants. Warmups precede measured repetitions.
 */
#ifndef ARCH
#error Build with ARCH=0,1,2
#endif
#include <stdint.h>
#include "ldacs.h"
#if ARCH == 2
#include "receiver.h"
#endif

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
        "2: mrc p15, 0, r0, c1, c0, 2\n"
        "orr r0, r0, #0x00f00000\n"
        "mcr p15, 0, r0, c1, c0, 2\n"
        "isb\n"
        "mov r0, #0x40000000\n"
        "vmsr fpexc, r0\n"
        "b bridge_main\n"
        ".ltorg\n"
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
#define DEC_TRACE_SEL   0x28
#define DEC_VIT_CYCLES  0x2C
#define DEC_BDI_CYCLES  0x30
#define DEC_RS_CYCLES   0x34
#define DEC_PIPE_CYCLES 0x38
#define DEC_FREE_CYCLES 0x3C

/* Actual FCLK_CLK0 frequency emitted by the current Vivado design. */
#define PL_CLOCK_HZ     pl_clock_hz
static uint32_t pl_clock_hz;

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
static uint8_t helical_trace[TX_BUF_MAX];
static uint8_t final_data[RX_BUF_MAX];
static uint8_t viterbi_trace[RX_BUF_MAX];
static uint8_t block_trace[RX_BUF_MAX];
static uint8_t rs_trace[RX_BUF_MAX];

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

static void uart_put_u32(uint32_t v)
{
    uart_putc((uint8_t)(v & 0xFF));
    uart_putc((uint8_t)((v >> 8) & 0xFF));
    uart_putc((uint8_t)((v >> 16) & 0xFF));
    uart_putc((uint8_t)((v >> 24) & 0xFF));
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

static void copy_from_dma(uint8_t *dst, const volatile uint8_t *src, uint32_t len)
{
    for (uint32_t i = 0; i < len; i++) dst[i] = src[i];
}

/* -----------------------------------------------------------------------
 * AXI DMA helpers
 * --------------------------------------------------------------------- */
#if ARCH != 2
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
    __asm volatile("dsb sy" ::: "memory");
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
        if (sr & DMASR_IOC) {__asm volatile("dsb sy" ::: "memory");return 0;}   /* done */
        if ((sr | rreg(DMA_BASE + MM2S_DMASR)) & DMASR_ERRS) return -1; /* error */
    }
    return -2;  /* timeout */
}

static int run_decoder_tap(uint8_t mode, uint16_t n_coded, uint16_t n_steps,
                           uint16_t num_cw, uint8_t rs_n, uint8_t trace_sel,
                           uint16_t trace_len)
{
    wreg(DEC_BASE + DEC_CTRL, 0x1);
    volatile int r = 0; for (r = 0; r < 1000; r++);
    wreg(DEC_BASE + DEC_CTRL, 0x0);
    wreg(DEC_BASE + DEC_RATE, mode);
#if ARCH == 1
    wreg(DEC_BASE + 0x4C, n_coded);
#endif
    wreg(DEC_BASE + DEC_N_STEPS, n_steps);
    wreg(DEC_BASE + DEC_NUM_CW, num_cw);
    wreg(DEC_BASE + DEC_RS_N, rs_n);
    wreg(DEC_BASE + DEC_TRACE_SEL, trace_sel);
    dma_reset();
    return dma_transfer(DMA_TX_PHYS, n_coded, DMA_RX_PHYS, trace_len);
}

#endif

/* Cortex-A9 global timer, CPU/2, no prescaler. 64-bit reads survive low-word wrap. */
static uint64_t ticks(void) {
    __asm volatile("dsb sy\n\tisb" ::: "memory");
    uint32_t hi,lo,end;
    do {hi=rreg(0xF8F00204);lo=rreg(0xF8F00200);end=rreg(0xF8F00204);}while(hi!=end);
    __asm volatile("dmb sy" ::: "memory");
    return ((uint64_t)hi<<32)|lo;
}
static uint32_t timer_hz(void) {
    uint32_t clk=rreg(0xF8000120),src=(clk>>4)&3,div=(clk>>8)&63;
    uint32_t pll=rreg(src==2?0xF8000104:src==3?0xF8000108:0xF8000100);
    uint32_t feedback=(pll>>12)&127;
    if(!div||!feedback||(pll&3))return 0;
    /* Nominal 33.333333 MHz board oscillator. PLL bypass-force bit 4. */
    uint64_t hz=(uint64_t)33333333u*((pll&(1u<<4))?1:feedback);
    return (uint32_t)(hz/div/2);
}
static uint32_t fabric_hz(void) {
#if ARCH == 2
    return 0;
#else
    uint32_t c=rreg(0xF8000170),src=(c>>4)&3,d0=(c>>8)&63,d1=(c>>20)&63;
    uint32_t pll=rreg(src==2?0xF8000100:src==3?0xF8000104:0xF8000108);
    unsigned feedback=(pll>>12)&127;
    if(!d0||!d1||!feedback||(pll&3))return 0;
    return (uint32_t)((uint64_t)33333333u*((pll&(1u<<4))?1:feedback)/d0/d1);
#endif
}
static void put64(uint64_t v) {uart_put_u32((uint32_t)v);uart_put_u32((uint32_t)(v>>32));}
static uint32_t get32(void) {uint32_t lo=uart_get_u16();return lo|((uint32_t)uart_get_u16()<<16);}
static uint32_t crc32(const uint8_t *p,unsigned n) {
    uint32_t c=0xffffffffu;
    for(unsigned i=0;i<n;i++) {c^=p[i];for(unsigned b=0;b<8;b++)c=(c>>1)^((0u-(c&1))&0xedb88320u);}
    return ~c;
}
#include "dpr_runtime.inc"
static void error(void) {uart_put_u32(0xffffffffu);}
typedef struct {uint64_t stage[5],elapsed,pipe;uint32_t corr,fail;} measurement;
static int valid(unsigned rate,unsigned coded,unsigned steps,unsigned cw,unsigned n,unsigned payload) {
    if(rate>2||n!=101||(coded!=9768&&coded!=19536&&coded!=29304))return 0;
    if(coded==19536&&rate==2)return 0;
    unsigned expected=rate==0?coded/2:rate==1?(coded/3)*2:(coded/4)*3;
    return steps==expected&&cw==(steps-6)/(8*n)&&payload==cw*(n-10)&&
        steps<=22016&&cw*n<=4096&&payload>0;
}
/* PL counters are inclusive accepted-input to accepted-output latencies.
 * PS stages and whole-board decoder latency use global timer ticks. */
static int decode(unsigned rate,unsigned coded,unsigned steps,unsigned cw,unsigned n,unsigned payload,
                  int trace,measurement *m) {
    if(!dpr_identity())return -1;
    for(unsigned i=0;i<5;i++)m->stage[i]=0;
    m->corr=0;m->fail=0;m->pipe=0;
    unsigned nrs=cw*n;
#if ARCH != 2
    if(trace) {
#if ARCH == 0
        helical_deinterleave(helical_buf,(uint8_t *)tx_buf,coded);
#endif
#if ARCH == 1
        if(run_decoder_tap(rate,coded,steps,cw,n,3,coded))return -1;
        copy_from_dma(helical_trace,rx_buf,coded);
#endif
        if(run_decoder_tap(rate,coded,steps,cw,n,1,nrs))return -1;
        copy_from_dma(viterbi_trace,rx_buf,nrs);
        if(run_decoder_tap(rate,coded,steps,cw,n,2,nrs))return -1;
        copy_from_dma(block_trace,rx_buf,nrs);
#if ARCH == 1
        if(run_decoder_tap(rate,coded,steps,cw,n,4,payload))return -1;
        copy_from_dma(rs_trace,rx_buf,payload);
#endif
    }
#endif
    uint64_t start=ticks(),a=start;
#if ARCH == 2
    rx_config cfg={rate,coded,steps,cw,n,payload};
    helical_deinterleave(helical_buf,helical_trace,coded);
    m->stage[0]=ticks()-a;a=ticks();
    if(rx_viterbi(helical_trace,viterbi_trace,&cfg))return -1;
    m->stage[1]=ticks()-a;a=ticks();
    rx_block_deinterleave(viterbi_trace,block_trace,&cfg);
    m->stage[2]=ticks()-a;a=ticks();
    for(unsigned i=0;i<cw;i++) {
        unsigned corr=0;
        int status=rx_rs_word(block_trace+i*n,rs_trace+i*(n-10),n,&corr);
        if(status<0)return -1;
        m->corr+=corr;m->fail+=(unsigned)(status!=0);
    }
    m->stage[3]=ticks()-a;a=ticks();
    derandomize(rs_trace,final_data,payload);
    m->stage[4]=ticks()-a;
#else
#if ARCH == 0
    helical_deinterleave(helical_buf,(uint8_t *)tx_buf,coded);
    m->stage[0]=ticks()-a;
#endif
    wreg(DEC_BASE+DEC_CTRL,2);
    if(run_decoder_tap(rate,coded,steps,cw,n,0,payload))return -1;
    m->stage[1]=rreg(DEC_BASE+DEC_VIT_CYCLES);
    m->stage[2]=rreg(DEC_BASE+DEC_BDI_CYCLES);
    m->stage[3]=rreg(DEC_BASE+DEC_RS_CYCLES);
    m->pipe=rreg(DEC_BASE+DEC_PIPE_CYCLES);
    m->corr=rreg(DEC_BASE+DEC_RS_CORR);m->fail=rreg(DEC_BASE+DEC_RS_FAIL);
#if ARCH == 0
    if(trace)copy_from_dma(rs_trace,rx_buf,payload);
    a=ticks();derandomize((const uint8_t *)rx_buf,(uint8_t *)rx_buf,payload);
    m->stage[4]=ticks()-a;
#else
    m->stage[0]=rreg(DEC_BASE+0x40);m->stage[4]=rreg(DEC_BASE+0x44);
#endif
#endif
    m->elapsed=ticks()-start;
#if ARCH != 2
    copy_from_dma(final_data,rx_buf,payload);
#if ARCH == 0
    if(trace)copy_from_dma(helical_trace,tx_buf,coded);
#endif
#endif
    return 0;
}
void bridge_main(void) {
    disable_caches();uart_init_115200();
    /* Enable the global timer, preserving its count. Prescaler=0. */
    wreg(0xF8F00208,1);
    uint32_t gt_hz=timer_hz();pl_clock_hz=fabric_hz();
    wreg(0xF8000008,0xdf0d);wreg(0xF8000900,15);wreg(0xF8000240,0);
    if(rreg(DPR_REG(0x8c))!=0x44505231u)for(;;)uart_put_u32(0xffffffffu);
    wreg(DPR_REG(0x80),0);
    for(volatile unsigned settle=0;settle<128;settle++)__asm volatile("nop");

#if ARCH == 2
    rx_init();
#else
    wreg(0xF8000008,0xDF0D);wreg(0xF8000900,0x0F);wreg(0xF8000240,0);
    if(rreg(DEC_BASE+DEC_VERSION)!=(ARCH==1?0x46504c31u:0x4c444333u))for(;;)error();
#endif
    if(!gt_hz||(ARCH!=2&&!pl_clock_hz))for(;;)error();
    for(;;) {
        /* Sliding 4-byte sync tolerates noise and partial headers. */
        uint32_t magic=0;
        do{magic=(magic<<8)|uart_getc();}while(magic!=0x4c444143u&&magic!=0x4c444231u&&magic!=0x44505331u&&magic!=0x44505531u&&magic!=0x44505231u);
        if(magic==0x44505331u){dpr_status();continue;}
        if(magic==0x44505531u){dpr_upload();continue;}
        if(magic==0x44505231u){dpr_switch();continue;}
        if(!dpr_identity()){error();continue;}
        unsigned batch=magic==0x4c444231u;
        unsigned rate=uart_getc(),coded=uart_get_u16(),payload=uart_get_u16();
        unsigned steps=uart_get_u16(),cw=uart_get_u16(),n=uart_getc();
        unsigned reps=1,warmups=0;uint32_t expected_crc=0;
        if(batch){reps=uart_get_u16();warmups=uart_get_u16();expected_crc=get32();}
        if(!valid(rate,coded,steps,cw,n,payload)||!reps||reps>1000||warmups>100){error();continue;}
        uart_read_buf(helical_buf,coded);
#if ARCH == 1
        /* Transport copy is excluded from decoder timing, just as UART RX is.
         * FULL_PL receives the original helical-interleaved frame. */
        for(unsigned i=0;i<coded;i++)tx_buf[i]=helical_buf[i];
#endif
        measurement m;
        int failed=0;
        for(unsigned i=0;i<warmups;i++)if(decode(rate,coded,steps,cw,n,payload,0,&m)){failed=1;break;}
        if(failed){error();continue;}
        uint64_t sums[5]={0},total=0,minimum=~(uint64_t)0,maximum=0,pipe=0;
        uint32_t corrections=0,failures=0,bad=0;
        for(unsigned run=0;run<reps;run++) {
            if(decode(rate,coded,steps,cw,n,payload,!batch,&m)){failed=1;break;}
            for(unsigned j=0;j<5;j++)sums[j]+=m.stage[j];
            total+=m.elapsed;pipe+=m.pipe;
            if(m.elapsed<minimum)minimum=m.elapsed;
            if(m.elapsed>maximum)maximum=m.elapsed;
            corrections+=m.corr;failures+=m.fail;
            if(batch&&crc32(final_data,payload)!=expected_crc)bad++;
        }
        if(failed){error();continue;}
        if(batch) {
            uart_putc('D');uart_putc('D');uart_putc('B');uart_putc('R');
            uart_putc(ARCH);uart_putc(rate);uart_put_u16(reps);uart_put_u16(payload);uart_put_u16(warmups);
            uart_put_u32(gt_hz);uart_put_u32(PL_CLOCK_HZ);
            uart_put_u32(corrections);uart_put_u32(failures);uart_put_u32(bad);
            for(unsigned j=0;j<5;j++)put64(sums[j]);
            put64(total);put64(minimum);put64(maximum);put64(pipe);
            uart_write_buf(final_data,payload);
        } else {
            uart_putc('D');uart_putc('T');uart_putc('R');uart_putc('4');uart_putc(ARCH);
            uart_put_u16(coded);uart_put_u16(cw*n);uart_put_u16(cw*n);
            uart_put_u16(payload);uart_put_u16(payload);uart_put_u16(corrections);uart_put_u16(failures);
            for(unsigned j=0;j<5;j++) {
                uint64_t v=sums[j];
#if ARCH != 2
                if((ARCH==1)||(j>=1&&j<=3))v=v*gt_hz/PL_CLOCK_HZ;
#endif
                /* TRC3 order: helical,vit,block,RS,pipeline,derand,board,hz */
                if(j==4) {
                    #if ARCH == 2
                    uart_put_u32((uint32_t)total);
#else
                    uart_put_u32((uint32_t)(pipe*gt_hz/PL_CLOCK_HZ));
#endif
                }
                uart_put_u32((uint32_t)v);
            }
            uart_put_u32((uint32_t)total);uart_put_u32(gt_hz);
            uart_write_buf(helical_trace,coded);uart_write_buf(viterbi_trace,cw*n);
            uart_write_buf(block_trace,cw*n);uart_write_buf(rs_trace,payload);uart_write_buf(final_data,payload);
        }
    }
}

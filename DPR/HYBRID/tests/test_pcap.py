"""Execute actual PCAP driver logic against register fixtures, never FPGA timing."""
import ctypes
import os
from pathlib import Path
import subprocess
import unittest
ROOT = Path(__file__).resolve().parents[1]

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = ROOT / 'build/pcap_driver_test'; out.mkdir(parents=True, exist_ok=True)
        source = r'''
#include <stdint.h>
#define ARCH 1
#define DPR_BARRIER() ((void)0)
static uint32_t rreg(uint32_t a);
static void wreg(uint32_t a,uint32_t v);
static uint64_t ticks(void);
static void uart_putc(uint8_t x){(void)x;}
static void uart_put_u32(uint32_t x){(void)x;}
static void put64(uint64_t x){(void)x;}
static unsigned uart_getc(void){return 0;}
static uint32_t get32(void){return 0;}
static void uart_read_buf(volatile uint8_t *p,uint32_t n){(void)p;(void)n;}
static uint32_t timer_hz(void){return 100;}
static uint32_t crc32(const uint8_t *p,unsigned n){(void)p;(void)n;return 0;}
#include "dpr_runtime.inc"
static uint32_t control,mode,started,writes_addr[32],writes_value[32],nw;
static uint64_t counter;
static uint32_t rreg(uint32_t a){
 if(a==DEVCFG)return control;
 if(a==DEVCFG+0x14){
  if(mode==1)return 0x80000010;
  if(mode==2)return 0;
  if(mode==5&&started)return 0;
  return 0x40000010;
 }
 if(a==DEVCFG+0x0c)return mode==3?0x40:mode==4?0:0x3000;
 return 0;
}
static void wreg(uint32_t a,uint32_t v){
 if(nw<32){writes_addr[nw]=a;writes_value[nw]=v;nw++;}
 if(a==DEVCFG)control=v;
 if(a==DEVCFG+0x24)started=1;
}
static uint64_t ticks(void){counter+=200;return counter;}
int exercise(unsigned test){
 mode=test;control=test==6?0:0x40000000;counter=0;nw=0;started=0;
 image_size[1]=16;uint32_t flags=0;return pcap_load(1,100,&flags);
}
int blocked_retry(void){pcap_fault=1;nw=0;dpr_switch();return (int)last_dpr_error;}
unsigned write_count(void){return nw;}
unsigned write_address(unsigned i){return writes_addr[i];}
unsigned write_value(unsigned i){return writes_value[i];}
'''
        c = out / 'driver_fixture.c'; c.write_text(source)
        dll = out / ('driver.dll' if os.name == 'nt' else 'driver.so')
        subprocess.run(['gcc', '-std=c11', '-O2', '-shared', *([] if os.name == 'nt' else ['-fPIC']),
                        '-I' + str(ROOT / 'sw/src'), str(c), '-o', str(dll)], check=True)
        cls.lib = ctypes.CDLL(str(dll))
        for name in ('write_count', 'write_address', 'write_value'): getattr(cls.lib, name).restype = ctypes.c_uint
    def test_native_driver_programming_sequence(self):
        self.assertEqual(self.lib.exercise(0), 0)
        writes = [(self.lib.write_address(i), self.lib.write_value(i)) for i in range(self.lib.write_count())]
        self.assertEqual(writes[0], (0xf8007034, 0x757bdf0d))
        self.assertIn((0xf8007018, 0x03800001), writes)
        self.assertIn((0xf800701c, 0xffffffff), writes)
        self.assertIn((0xf8007020, 4), writes)  # words, not bytes
        self.assertIn((0xf8007024, 0), writes)
        ctrl = [v for a, v in writes if a == 0xf8007000]
        self.assertTrue(all(v & 0x40000000 for v in ctrl))  # never reset entire PL
        self.assertTrue(all(v & 0x0c000000 == 0x0c000000 for v in ctrl))
    def test_fault_latch_blocks_new_transfer(self):
        self.assertEqual(self.lib.blocked_retry(),16)
        self.assertEqual(self.lib.write_count(),0)
    def test_queue_full_rejected(self): self.assertEqual(self.lib.exercise(1), 11)
    def test_initialization_not_ready(self): self.assertEqual(self.lib.exercise(2), 11)
    def test_error_interrupt(self): self.assertEqual(self.lib.exercise(3), 12)
    def test_timeout(self): self.assertEqual(self.lib.exercise(4), 14)
    def test_configuration_init_falls(self): self.assertEqual(self.lib.exercise(5), 13)
    def test_program_b_already_low(self): self.assertEqual(self.lib.exercise(6), 10)
if __name__ == '__main__': unittest.main()

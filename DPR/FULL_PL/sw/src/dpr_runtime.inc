/* Bare-metal Zynq-7000 PCAP partial loading. No global PL reset is issued.
 * Register contract: AMD UG585 and embeddedsw xdevcfg v2022.2 (see docs).
 * Only unencrypted, verified same-shell .pcap.bin images are accepted by host.
 */
#ifndef DPR_BARRIER
#define DPR_BARRIER() __asm volatile("dsb sy" ::: "memory")
#endif
#define DPR_REG(off) (0x40000000u+(off))
#define DEVCFG 0xF8007000u
#define IMAGE_BASE 0x03000000u
#define IMAGE_STRIDE 0x00800000u
static uint32_t image_size[4],image_crc[4],image_token[4],last_dpr_error,pcap_fault;
static void dpr_magic(const char *s){for(unsigned i=0;i<4;i++)uart_putc((uint8_t)s[i]);}
static void dpr_error(uint32_t code){last_dpr_error=code;dpr_magic("DPRE");uart_put_u32(code);}
static int dpr_identity(void){
 return rreg(DPR_REG(0x8c))==0x44505231u&&rreg(DPR_REG(0x80))==0&&rreg(DPR_REG(0x88))==ARCH;
}
static int dma_idle(void){
 uint32_t a=rreg(0x40400004),b=rreg(0x40400034);
 return ((a&3)!=0)&&((b&3)!=0)&&!(a&0x770)&&!(b&0x770);
}
static void dpr_status(void){
 dpr_magic("DPSR");uart_put_u32(ARCH);uart_put_u32(rreg(DPR_REG(0x8c)));
 uart_put_u32(rreg(DPR_REG(0x94)));uart_put_u32(rreg(DPR_REG(0x88)));
 uart_put_u32(rreg(DPR_REG(0x80)));uart_put_u32(rreg(DPR_REG(0x90)));
 uart_put_u32(timer_hz());uart_put_u32(last_dpr_error);
}
static void dpr_upload(void){
 unsigned id=uart_getc();uint32_t token=get32(),size=get32(),expected=get32();
 if(id>3||!size||size>IMAGE_STRIDE||(size&3)||token!=rreg(DPR_REG(0x94))){dpr_error(1);return;}
 image_size[id]=0;dpr_magic("RDY1");
 uint8_t *data=(uint8_t *)(uintptr_t)(IMAGE_BASE+id*IMAGE_STRIDE);
 uart_read_buf(data,size);DPR_BARRIER();
 if(crc32(data,size)!=expected){dpr_error(2);return;}
 /* PCAP reads native little-endian words; verify a synchronized packet stream. */
 int sync=0;for(unsigned i=0;i+4<=size&&i<1024;i+=4)
  if(*(uint32_t *)(data+i)==0xaa995566u){sync=1;break;}
 if(!sync){dpr_error(3);return;}
 image_size[id]=size;image_crc[id]=expected;image_token[id]=token;
 dpr_magic("DPUA");uart_put_u32(id);uart_put_u32(size);uart_put_u32(expected);
}
static int pcap_load(unsigned id,uint32_t hz,uint32_t *interrupts){
 uint32_t address=IMAGE_BASE+id*IMAGE_STRIDE;
 wreg(DEVCFG+0x34,0x757bdf0du); /* first DevCfg access is UNLOCK */
 wreg(0xF8000008,0xdf0d);wreg(0xF8000168,rreg(0xF8000168)|1u);
 uint32_t ctrl=rreg(DEVCFG);
 if(!(ctrl&0x40000000u))return 10; /* never pulse PROGRAM_B for a partial load */
 wreg(DEVCFG,(ctrl|0x0c000000u)&~0x02000000u);
 wreg(DEVCFG+0x80,rreg(DEVCFG+0x80)&~0x10u); /* disable loopback */
 wreg(DEVCFG+0x08,rreg(DEVCFG+0x08)&~0x30u); /* increment DDR addresses */
 uint32_t status=rreg(DEVCFG+0x14);
 if(!(status&0x10u)||(status&0x80000000u))return 11;
 wreg(DEVCFG+0x0c,0x00f7f8efu);
 DPR_BARRIER();
 wreg(DEVCFG+0x18,address|1u);wreg(DEVCFG+0x1c,0xffffffffu);
 wreg(DEVCFG+0x20,image_size[id]/4);wreg(DEVCFG+0x24,0);
 uint64_t start=ticks();
 for(;;){
  uint32_t flags=rreg(DEVCFG+0x0c);*interrupts=flags;
  if(flags&0x00f4c840u)return 12;
  if(!(rreg(DEVCFG+0x14)&0x10u))return 13;
  if((flags&0x3000u)==0x3000u)break; /* DMA AND PCAP drained */
  if(ticks()-start>(uint64_t)hz*10)return 14;
 }
 DPR_BARRIER();return 0;
}
static void dpr_switch(void){
 unsigned id=uart_getc();uint64_t command_start=ticks();uint32_t hz=timer_hz(),flags=0;
 if(pcap_fault){dpr_error(16);return;}
 if(id>3||!image_size[id]||image_token[id]!=rreg(DPR_REG(0x94))){dpr_error(4);return;}
 /* CRC is checked again before timing; upload/verification time is separate. */
 if(crc32((const uint8_t *)(uintptr_t)(IMAGE_BASE+id*IMAGE_STRIDE),image_size[id])!=image_crc[id]){dpr_error(5);return;}
 uint64_t precheck=ticks()-command_start;
 uint32_t before=rreg(DPR_REG(0x88));uint64_t start=ticks(),a=start;
 if((rreg(DPR_REG(0x84))&4)||!dma_idle()){dpr_error(6);return;}
 wreg(DPR_REG(0x80),3);DPR_BARRIER();
 if(rreg(DPR_REG(0x80))!=3){dpr_error(7);return;}
 uint64_t isolated_at=ticks();uint64_t isolation=isolated_at-a;
 a=ticks();int code=pcap_load(id,hz,&flags);uint64_t load=ticks()-a;
 if(code){pcap_fault=1;dpr_error((uint32_t)code);return;} /* partition remains isolated/reset */
 a=ticks();
 /* Manual reset covers all RM sequential state. Identity output is combinational. */
 for(volatile unsigned i=0;i<128;i++)__asm volatile("nop");
 if(rreg(DPR_REG(0x98))!=id){pcap_fault=1;dpr_error(15);return;}
 wreg(DPR_REG(0x80),0);DPR_BARRIER();
 for(volatile unsigned i=0;i<128;i++)__asm volatile("nop");
 if(rreg(DPR_REG(0x88))!=id||rreg(DPR_REG(0x80))!=0){pcap_fault=1;wreg(DPR_REG(0x80),3);dpr_error(15);return;}
 uint64_t stop=ticks();
 uint64_t restart=stop-a,total=stop-start,downtime=stop-isolated_at;
 last_dpr_error=0;dpr_magic("DPRR");
 uart_put_u32(before);uart_put_u32(id);uart_put_u32(rreg(DPR_REG(0x94)));
 uart_put_u32(rreg(DPR_REG(0x90)));uart_put_u32(hz);uart_put_u32(image_size[id]);uart_put_u32(flags);
 put64(isolation);put64(load);put64(restart);put64(total);put64(downtime);put64(precheck);put64(stop-command_start);
}

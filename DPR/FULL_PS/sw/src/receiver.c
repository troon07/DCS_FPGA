/* Complete C receive algorithms, matching model/ldacs_ref.py including ties,
 * terminated traceback, GF polynomial 0x11d, FCR=0 and ten parity symbols.
 * No heap, operating system, DMA, FPGA registers or floating point. */
#include "receiver.h"
static uint64_t history[RX_MAX_STEPS];
static uint8_t decoded[RX_MAX_STEPS];
static uint8_t gx[128], gy[128], exp_table[512], log_table[256];

static unsigned parity(unsigned v) {
    v ^= v >> 4; v ^= v >> 2; v ^= v >> 1; return v & 1;
}
void rx_init(void) {
    unsigned x=1;
    for (unsigned i=0;i<255;i++) {
        exp_table[i]=(uint8_t)x; log_table[x]=(uint8_t)i;
        x<<=1; if(x&256) x^=0x11d;
    }
    for(unsigned i=255;i<512;i++) exp_table[i]=exp_table[i-255];
    for(unsigned i=0;i<128;i++) {gx[i]=(uint8_t)parity(i&0171);gy[i]=(uint8_t)parity(i&0133);}
}
static uint8_t mul(uint8_t a,uint8_t b) {
    return (!a||!b)?0:exp_table[(unsigned)log_table[a]+log_table[b]];
}
static uint8_t inv(uint8_t a) {return a?exp_table[255-log_table[a]]:0;}

int rx_viterbi(const uint8_t *in,uint8_t *out,const rx_config *c) {
    if(c->rate>2||c->steps>RX_MAX_STEPS||c->steps<6) return -1;
    unsigned nout=c->codewords*c->rs_n*8;
    if(nout>c->steps-6) return -1;
    uint16_t pm[64], next[64];
    for(unsigned s=0;s<64;s++) pm[s]=s?32:0;
    unsigned idx=0;
    for(unsigned k=0;k<c->steps;k++) {
        unsigned ph=k%(c->rate+1), ex=1,ey=1,x=0,y=0;
        if(c->rate==1) ex=(ph==0);
        if(c->rate==2) {ex=(ph!=1);ey=(ph!=2);}
        if(idx+ex+ey>c->coded) return -1;
        if(ex) x=in[idx++]&1;
        if(ey) y=in[idx++]&1;
        uint64_t decisions=0;unsigned minimum=65535;
        for(unsigned ns=0;ns<64;ns++) {
            unsigned r0=ns*2,r1=r0+1;
            unsigned m0=pm[(ns&31)*2]+(ex&(x^gx[r0]))+(ey&(y^gy[r0]));
            unsigned m1=pm[(ns&31)*2+1]+(ex&(x^gx[r1]))+(ey&(y^gy[r1]));
            unsigned m=m0;
            if(m1<m0){m=m1;decisions|=(uint64_t)1<<ns;}
            next[ns]=(uint16_t)m;if(m<minimum) minimum=m;
        }
        for(unsigned s=0;s<64;s++) pm[s]=(uint16_t)(next[s]-minimum);
        history[k]=decisions;
    }
    if(idx!=c->coded) return -1;
    unsigned state=0;
    for(unsigned k=c->steps;k-->0;) {
        decoded[k]=(uint8_t)(state>>5);
        state=((state&31)<<1)|(unsigned)((history[k]>>state)&1);
    }
    for(unsigned b=0;b<nout/8;b++) {
        unsigned v=0;for(unsigned k=0;k<8;k++)v=(v<<1)|decoded[b*8+k];out[b]=(uint8_t)v;
    }
    return 0;
}
void rx_block_deinterleave(const uint8_t *in,uint8_t *out,const rx_config *c) {
    for(unsigned cw=0;cw<c->codewords;cw++)
        for(unsigned p=0;p<c->rs_n;p++)out[cw*c->rs_n+p]=in[p*c->codewords+cw];
}
int rx_rs_word(const uint8_t *in,uint8_t *out,unsigned n,unsigned *corrected) {
    uint8_t synd[10],lam[11]={1},b[11]={1},next[11],omega[10],word[255];
    unsigned any=0;*corrected=0;
    if(n<=10||n>255)return -1;
    for(unsigned i=0;i<n;i++)word[i]=in[i];
    for(unsigned j=0;j<10;j++) {
        uint8_t s=0;for(unsigned p=0;p<n;p++)s=mul(s,exp_table[j])^in[p];
        synd[j]=s;any|=s;
    }
    unsigned L=0,m=1;uint8_t bb=1;
    if(any) {
        for(unsigned r=0;r<10;r++) {
            uint8_t d=synd[r];
            for(unsigned i=1;i<=L&&i<=r;i++)d^=mul(lam[i],synd[r-i]);
            if(!d){m++;continue;}
            uint8_t coef=mul(d,inv(bb));
            for(unsigned i=0;i<=10;i++)next[i]=lam[i]^((i>=m)?mul(coef,b[i-m]):0);
            if(2*L<=r){for(unsigned i=0;i<=10;i++)b[i]=lam[i];L=r+1-L;bb=d;m=1;}else m++;
            for(unsigned i=0;i<=10;i++)lam[i]=next[i];
        }
        if(L>5) goto fail;
        for(unsigned i=0;i<10;i++) {
            uint8_t v=0;for(unsigned j=0;j<=i;j++)v^=mul(synd[i-j],lam[j]);omega[i]=v;
        }
        unsigned roots=0,positions[5];uint8_t values[5];
        for(unsigned p=0;p<n;p++) {
            uint8_t sum=0,odd=0,osum=0;
            for(unsigned j=0;j<=10;j++){
                uint8_t t=mul(lam[j],exp_table[(j*(255-p))%255]);sum^=t;if(j&1)odd^=t;
            }
            if(sum)continue;
            for(unsigned j=0;j<10;j++)osum^=mul(omega[j],exp_table[(j*(255-p))%255]);
            if(!odd||roots>=5)goto fail;
            positions[roots]=n-1-p;values[roots]=mul(osum,inv(odd));roots++;
        }
        if(roots!=L)goto fail;
        for(unsigned i=0;i<roots;i++)word[positions[i]]^=values[i];
        *corrected=roots;
    }
    for(unsigned i=0;i<n-10;i++)out[i]=word[i];
    return 0;
fail:
    for(unsigned i=0;i<n-10;i++)out[i]=in[i];
    return 1;
}

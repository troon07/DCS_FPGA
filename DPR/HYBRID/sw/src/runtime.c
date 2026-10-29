#include <stddef.h>
void *memset(void *dst,int value,size_t n){unsigned char *p=dst;for(size_t i=0;i<n;i++)p[i]=(unsigned char)value;return dst;}
void *memcpy(void *dst,const void *src,size_t n){unsigned char *d=dst;const unsigned char *s=src;for(size_t i=0;i<n;i++)d[i]=s[i];return dst;}

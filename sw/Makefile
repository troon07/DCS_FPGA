# LDACS decoder software
#   make            -> cross-compile for ZedBoard (ARM Cortex-A9, Linux)
#   make host-test  -> build + run software block tests on your PC
#
# Cross compiler: from PetaLinux/Vitis ("arm-linux-gnueabihf-") or
# Ubuntu: sudo apt install gcc-arm-linux-gnueabihf
CROSS_COMPILE ?= arm-linux-gnueabihf-
CFLAGS  ?= -O3 -Wall -Wextra -Wno-missing-field-initializers -Iinclude
ARMFLAGS = -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard
SRC_COMMON = src/modes.c src/helical.c src/derand.c

all: ldacs_decode

ldacs_decode: $(SRC_COMMON) src/ldacs_hw.c src/main.c include/ldacs.h
	$(CROSS_COMPILE)gcc $(CFLAGS) $(ARMFLAGS) -o $@ $(SRC_COMMON) src/ldacs_hw.c src/main.c

test_host: $(SRC_COMMON) src/test_host.c include/ldacs.h
	gcc $(CFLAGS) -o $@ $(SRC_COMMON) src/test_host.c

host-test: test_host
	@for m in qpsk_1_2 qpsk_3_4 16qam_2_3 64qam_3_4; do \
	  python3 ../model/ldacs_ref.py --mode $$m --seed 11 --out ../build/tv_host_$$m >/dev/null && \
	  echo "== $$m" && ./test_host $$m ../build/tv_host_$$m || exit 1; \
	done

clean:
	rm -f ldacs_decode test_host
.PHONY: all host-test clean

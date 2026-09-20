# Linux on the ZedBoard (PetaLinux)

Tested flow names are for PetaLinux 2020.2–2023.x. Commands are run on an Ubuntu PC.

## 1. Create the PetaLinux project from the Vivado export
```bash
petalinux-create -t project --template zynq -n ldacs_os
cd ldacs_os
petalinux-config --get-hw-description=../hw/vivado/build/ldacs_zed.xsa
#  -> Image Packaging Configuration -> Root filesystem type: EXT4 (SD card)
```

## 2. Add the u-dma-buf kernel module
```bash
petalinux-create -t modules --name u-dma-buf --enable
# replace the template source with the real driver
wget -O project-spec/meta-user/recipes-modules/u-dma-buf/files/u-dma-buf.c \
     https://raw.githubusercontent.com/ikwzm/udmabuf/master/u-dma-buf.c
```
Edit `project-spec/meta-user/recipes-modules/u-dma-buf/u-dma-buf.bb` so `SRC_URI`
lists `file://u-dma-buf.c`, and change the Makefile's `obj-m` to `u-dma-buf.o`.
Add `KERNEL_MODULE_AUTOLOAD += "u-dma-buf"` to the recipe.

## 3. Device tree
Copy `linux/system-user.dtsi` over
`project-spec/meta-user/recipes-bsp/device-tree/files/system-user.dtsi`.

## 4. Build and write the SD card
```bash
petalinux-build
petalinux-package --boot --fsbl images/linux/zynq_fsbl.elf --fpga images/linux/system.bit --u-boot --force
```
- SD partition 1 (FAT32): `BOOT.BIN`, `boot.scr`, `image.ub`
- SD partition 2 (ext4): extract `images/linux/rootfs.tar.gz`

Set the ZedBoard boot jumpers (JP7–JP11) to SD boot, connect the USB-UART (115200 baud), power on.

## 5. Check on the board
```bash
ls /dev/udmabuf_*                         # udmabuf_rx  udmabuf_tx
cat /sys/class/u-dma-buf/udmabuf_tx/phys_addr
```

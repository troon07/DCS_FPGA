/* ldacs_bridge.ld - Bare-metal linker script for Zynq PS ARM Cortex-A9
 *
 * Loads code + data into initialized DDR at 0x01000000.
 * Hardware probing on the connected EDGE Z7-10 shows its OCM JTAG aperture
 * aborts, while DDR is readable/writable after the generated PS init Tcl.
 * The image is deliberately above the DMA buffers at 0x00100000 and 0x00200000.
 */

ENTRY(_start)

MEMORY {
    DDR_IMAGE (rwx) : ORIGIN = 0x01000000, LENGTH = 16M
}

SECTIONS {
    . = ORIGIN(DDR_IMAGE);

    .text : {
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
    } > DDR_IMAGE

    .data : {
        *(.data*)
        . = ALIGN(4);
    } > DDR_IMAGE

    .bss : {
        __bss_start = .;
        *(.bss*)
        *(COMMON)
        __bss_end = .;
        . = ALIGN(4);
    } > DDR_IMAGE

    __stack_top = ORIGIN(DDR_IMAGE) + LENGTH(DDR_IMAGE);
}

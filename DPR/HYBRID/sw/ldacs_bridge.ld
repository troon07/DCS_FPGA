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

PHDRS { code PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }

SECTIONS {
    . = ORIGIN(DDR_IMAGE);

    .text : {
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
    } > DDR_IMAGE :code

    .data : {
        *(.data*)
        . = ALIGN(4);
    } > DDR_IMAGE :data

    .bss : {
        __bss_start = .;
        *(.bss*)
        *(COMMON)
        __bss_end = .;
        . = ALIGN(4);
    } > DDR_IMAGE :data

    __stack_top = ORIGIN(DDR_IMAGE) + LENGTH(DDR_IMAGE);
}

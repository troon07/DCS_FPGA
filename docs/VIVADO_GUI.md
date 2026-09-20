# Making the block design by hand (if create_project.tcl fails in your Vivado version)

1. **Create project** → RTL project → board *EdgeZ7_10* (part `xc7z010clg400-1`).
2. **Add sources** → all files in `hw/rtl/`.
3. **Create Block Design** named `system`.
4. Add **ZYNQ7 Processing System** → *Run Block Automation* (apply board preset).
   Double-click it:
   - PS-PL Configuration → HP Slave AXI Interface → enable **S AXI HP0**
   - Clock Configuration → PL Fabric Clocks → **FCLK_CLK0 = 70 MHz**
   - Interrupts → enable **Fabric interrupts → IRQ_F2P**
5. Add **AXI Direct Memory Access**. Double-click it:
   - untick *Enable Scatter Gather Engine*
   - *Width of Buffer Length Register* = **26**
   - Max burst size 256 for both channels
6. Right-click in the diagram → **Add Module** → `ldacs_decoder_top`.
7. Connect `dma/M_AXIS_MM2S → dec/s_axis` and `dec/m_axis → dma/S_AXIS_S2MM`.
8. *Run Connection Automation* → tick everything (connects AXI-Lite to GP0, DMA masters to HP0, clocks, resets).
9. Add **Concat** (2 inputs): `dma/mm2s_introut`, `dma/s2mm_introut` → `ps7/IRQ_F2P`.
10. **Address Editor** → note the addresses of `dma` and `dec` (the C program defaults are
    `0x40400000` and `0x43C00000`; pass `--dma`/`--dec` if yours differ).
11. Validate design (F6) → right-click `system.bd` → *Create HDL Wrapper* → *Generate Bitstream*.
12. File → Export → Export Hardware → include bitstream → `ldacs_zed.xsa`.

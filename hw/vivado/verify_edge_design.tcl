open_project build/ldacs_zed/ldacs_zed.xpr
open_bd_design build/ldacs_zed/ldacs_zed.srcs/sources_1/bd/system/system.bd
set ps [get_bd_cells ps7]
puts "BOARD_PART=[get_property BOARD_PART [current_project]]"
puts "PART=[get_property PART [current_project]]"
puts "UART0_ENABLED=[get_property CONFIG.PCW_UART0_PERIPHERAL_ENABLE $ps]"
puts "UART0_MIO=[get_property CONFIG.PCW_UART0_UART0_IO $ps]"
puts "FCLK0_MHZ=[get_property CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ $ps]"
puts "DMA=[get_property OFFSET [get_bd_addr_segs ps7/Data/SEG_dma_Reg]]"
puts "DECODER=[get_property OFFSET [get_bd_addr_segs ps7/Data/SEG_dec_reg0]]"
exit
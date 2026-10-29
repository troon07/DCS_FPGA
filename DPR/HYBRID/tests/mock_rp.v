module rp_decoder(
input wire  aclk,
input wire  aresetn,
input wire [7:0] s_axi_ctrl_awaddr,
input wire [2:0] s_axi_ctrl_awprot,
input wire  s_axi_ctrl_awvalid,
output wire  s_axi_ctrl_awready,
input wire [31:0] s_axi_ctrl_wdata,
input wire [3:0] s_axi_ctrl_wstrb,
input wire  s_axi_ctrl_wvalid,
output wire  s_axi_ctrl_wready,
output wire [1:0] s_axi_ctrl_bresp,
output wire  s_axi_ctrl_bvalid,
input wire  s_axi_ctrl_bready,
input wire [7:0] s_axi_ctrl_araddr,
input wire [2:0] s_axi_ctrl_arprot,
input wire  s_axi_ctrl_arvalid,
output wire  s_axi_ctrl_arready,
output wire [31:0] s_axi_ctrl_rdata,
output wire [1:0] s_axi_ctrl_rresp,
output wire  s_axi_ctrl_rvalid,
input wire  s_axi_ctrl_rready,
input wire [7:0] s_axis_tdata,
input wire  s_axis_tvalid,
output wire  s_axis_tready,
input wire  s_axis_tlast,
output wire [7:0] m_axis_tdata,
output wire  m_axis_tvalid,
input wire  m_axis_tready,
output wire  m_axis_tlast,
output wire [0:0] m_axis_tkeep,
output wire [31:0] rm_id
);
reg [31:0] identity=2;
assign rm_id=identity;
assign s_axis_tready=m_axis_tready;assign m_axis_tdata=s_axis_tdata;
assign m_axis_tvalid=s_axis_tvalid;assign m_axis_tlast=s_axis_tlast;assign m_axis_tkeep=1;
reg bv=0,rv=0;
wire wr=s_axi_ctrl_awvalid&&s_axi_ctrl_wvalid&&!bv;
assign s_axi_ctrl_awready=wr;assign s_axi_ctrl_wready=wr;
assign s_axi_ctrl_bvalid=bv;assign s_axi_ctrl_bresp=0;
assign s_axi_ctrl_arready=!rv;assign s_axi_ctrl_rvalid=rv;
assign s_axi_ctrl_rdata=32'h12345678;assign s_axi_ctrl_rresp=0;
always @(posedge aclk)begin
 if(!aresetn)begin bv<=0;rv<=0;end else begin
  if(bv&&s_axi_ctrl_bready)bv<=0;if(wr)bv<=1;
  if(rv&&s_axi_ctrl_rready)rv<=0;
  if(s_axi_ctrl_arvalid&&s_axi_ctrl_arready)rv<=1;
 end
end
endmodule

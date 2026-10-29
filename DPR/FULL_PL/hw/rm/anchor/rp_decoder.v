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

assign rm_id=3;
assign s_axis_tready=0;assign m_axis_tdata=0;assign m_axis_tvalid=0;assign m_axis_tlast=0;assign m_axis_tkeep=1;
reg bvalid,rvalid;reg [31:0] data,heartbeat;
wire wr=s_axi_ctrl_awvalid&&s_axi_ctrl_wvalid&&!bvalid;
assign s_axi_ctrl_awready=wr;assign s_axi_ctrl_wready=wr;
assign s_axi_ctrl_bvalid=bvalid;assign s_axi_ctrl_bresp=0;assign s_axi_ctrl_arready=!rvalid;
assign s_axi_ctrl_rvalid=rvalid;assign s_axi_ctrl_rdata=data;assign s_axi_ctrl_rresp=0;
always @(posedge aclk)begin
 if(!aresetn)begin bvalid<=0;rvalid<=0;data<=0;heartbeat<=0;end
 else begin
  heartbeat<=heartbeat+1'b1;
  if(bvalid&&s_axi_ctrl_bready)bvalid<=0;if(wr)bvalid<=1;
  if(rvalid&&s_axi_ctrl_rready)rvalid<=0;
  if(s_axi_ctrl_arvalid&&s_axi_ctrl_arready)begin
   rvalid<=1;data<=(s_axi_ctrl_araddr==8'h24)?32'h424c4e4b:
    (s_axi_ctrl_araddr==8'h04&&3==3)?heartbeat:0;
  end
 end
end
endmodule

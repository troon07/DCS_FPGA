// Static AXI-Lite proxy, frame-boundary isolation and local reset.
module dpr_shell #(parameter BUILD_TOKEN=32'h1)(
(* X_INTERFACE_PARAMETER="ASSOCIATED_BUSIF s_axi_ctrl:s_axis:m_axis, ASSOCIATED_RESET aresetn" *) input wire aclk,
(* X_INTERFACE_PARAMETER="POLARITY ACTIVE_LOW" *) input wire aresetn,
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
output wire [0:0] m_axis_tkeep
);

reg isolated,slot_reset,frame_active;
reg [31:0] generation;
wire slot_resetn=aresetn&&!isolated&&!slot_reset;
wire [31:0] module_id;
wire [7:0] rp_s_axi_ctrl_awaddr;
wire [2:0] rp_s_axi_ctrl_awprot;
wire  rp_s_axi_ctrl_awvalid;
wire  rp_s_axi_ctrl_awready;
wire [31:0] rp_s_axi_ctrl_wdata;
wire [3:0] rp_s_axi_ctrl_wstrb;
wire  rp_s_axi_ctrl_wvalid;
wire  rp_s_axi_ctrl_wready;
wire [1:0] rp_s_axi_ctrl_bresp;
wire  rp_s_axi_ctrl_bvalid;
wire  rp_s_axi_ctrl_bready;
wire [7:0] rp_s_axi_ctrl_araddr;
wire [2:0] rp_s_axi_ctrl_arprot;
wire  rp_s_axi_ctrl_arvalid;
wire  rp_s_axi_ctrl_arready;
wire [31:0] rp_s_axi_ctrl_rdata;
wire [1:0] rp_s_axi_ctrl_rresp;
wire  rp_s_axi_ctrl_rvalid;
wire  rp_s_axi_ctrl_rready;
wire [7:0] rp_s_axis_tdata;
wire  rp_s_axis_tvalid;
wire  rp_s_axis_tready;
wire  rp_s_axis_tlast;
wire [7:0] rp_m_axis_tdata;
wire  rp_m_axis_tvalid;
wire  rp_m_axis_tready;
wire  rp_m_axis_tlast;
wire [0:0] rp_m_axis_tkeep;
(* DONT_TOUCH="yes",KEEP_HIERARCHY="yes" *) rp_decoder rp(.aclk(aclk),.aresetn(slot_resetn),.s_axi_ctrl_awaddr(rp_s_axi_ctrl_awaddr),.s_axi_ctrl_awprot(rp_s_axi_ctrl_awprot),.s_axi_ctrl_awvalid(rp_s_axi_ctrl_awvalid),.s_axi_ctrl_awready(rp_s_axi_ctrl_awready),.s_axi_ctrl_wdata(rp_s_axi_ctrl_wdata),.s_axi_ctrl_wstrb(rp_s_axi_ctrl_wstrb),.s_axi_ctrl_wvalid(rp_s_axi_ctrl_wvalid),.s_axi_ctrl_wready(rp_s_axi_ctrl_wready),.s_axi_ctrl_bresp(rp_s_axi_ctrl_bresp),.s_axi_ctrl_bvalid(rp_s_axi_ctrl_bvalid),.s_axi_ctrl_bready(rp_s_axi_ctrl_bready),.s_axi_ctrl_araddr(rp_s_axi_ctrl_araddr),.s_axi_ctrl_arprot(rp_s_axi_ctrl_arprot),.s_axi_ctrl_arvalid(rp_s_axi_ctrl_arvalid),.s_axi_ctrl_arready(rp_s_axi_ctrl_arready),.s_axi_ctrl_rdata(rp_s_axi_ctrl_rdata),.s_axi_ctrl_rresp(rp_s_axi_ctrl_rresp),.s_axi_ctrl_rvalid(rp_s_axi_ctrl_rvalid),.s_axi_ctrl_rready(rp_s_axi_ctrl_rready),.s_axis_tdata(rp_s_axis_tdata),.s_axis_tvalid(rp_s_axis_tvalid),.s_axis_tready(rp_s_axis_tready),.s_axis_tlast(rp_s_axis_tlast),.m_axis_tdata(rp_m_axis_tdata),.m_axis_tvalid(rp_m_axis_tvalid),.m_axis_tready(rp_m_axis_tready),.m_axis_tlast(rp_m_axis_tlast),.m_axis_tkeep(rp_m_axis_tkeep),.rm_id(module_id));
assign rp_s_axis_tdata=s_axis_tdata;assign rp_s_axis_tlast=s_axis_tlast;
assign rp_s_axis_tvalid=s_axis_tvalid&&!isolated&&!slot_reset;
assign s_axis_tready=rp_s_axis_tready&&!isolated&&!slot_reset;
assign m_axis_tdata=isolated?8'd0:rp_m_axis_tdata;
assign m_axis_tvalid=rp_m_axis_tvalid&&!isolated&&!slot_reset;
assign m_axis_tlast=rp_m_axis_tlast&&!isolated&&!slot_reset;
assign m_axis_tkeep=1;assign rp_m_axis_tready=m_axis_tready&&!isolated&&!slot_reset;
wire input_fire=s_axis_tvalid&&s_axis_tready;
wire output_last=m_axis_tvalid&&m_axis_tready&&m_axis_tlast;
reg have_aw,have_w,bvalid,rvalid;
reg [7:0] awaddr,araddr;reg [31:0] wdata,rdata;reg [3:0] wstrb;
reg [1:0] bresp,rresp,ws,rs;reg sent_aw,sent_w;
assign s_axi_ctrl_awready=!have_aw&&ws==0&&!bvalid;
assign s_axi_ctrl_wready=!have_w&&ws==0&&!bvalid;
assign s_axi_ctrl_bvalid=bvalid;assign s_axi_ctrl_bresp=bresp;
assign s_axi_ctrl_arready=rs==0&&!rvalid;
assign s_axi_ctrl_rvalid=rvalid;assign s_axi_ctrl_rdata=rdata;assign s_axi_ctrl_rresp=rresp;
assign rp_s_axi_ctrl_awaddr=awaddr;assign rp_s_axi_ctrl_awprot=0;
assign rp_s_axi_ctrl_awvalid=ws==1&&!sent_aw&&!isolated&&!slot_reset;
assign rp_s_axi_ctrl_wdata=wdata;assign rp_s_axi_ctrl_wstrb=wstrb;
assign rp_s_axi_ctrl_wvalid=ws==1&&!sent_w&&!isolated&&!slot_reset;
assign rp_s_axi_ctrl_bready=ws==2&&!isolated&&!slot_reset;
assign rp_s_axi_ctrl_araddr=araddr;assign rp_s_axi_ctrl_arprot=0;
assign rp_s_axi_ctrl_arvalid=rs==1&&!isolated&&!slot_reset;
assign rp_s_axi_ctrl_rready=rs==2&&!isolated&&!slot_reset;
always @(posedge aclk)begin
 if(!aresetn)begin
  isolated<=1;slot_reset<=1;frame_active<=0;generation<=0;
  have_aw<=0;have_w<=0;bvalid<=0;rvalid<=0;bresp<=0;rresp<=0;
  ws<=0;rs<=0;sent_aw<=0;sent_w<=0;awaddr<=0;araddr<=0;wdata<=0;wstrb<=0;rdata<=0;
 end else begin
  if(input_fire)frame_active<=1;if(output_last)frame_active<=0;
  if(bvalid&&s_axi_ctrl_bready)bvalid<=0;if(rvalid&&s_axi_ctrl_rready)rvalid<=0;
  if(s_axi_ctrl_awvalid&&s_axi_ctrl_awready)begin have_aw<=1;awaddr<=s_axi_ctrl_awaddr;end
  if(s_axi_ctrl_wvalid&&s_axi_ctrl_wready)begin have_w<=1;wdata<=s_axi_ctrl_wdata;wstrb<=s_axi_ctrl_wstrb;end
  if(ws==0&&have_aw&&have_w&&!bvalid)begin
   have_aw<=0;have_w<=0;bresp<=0;
   if(awaddr[7])begin
    bvalid<=1;
    if(awaddr==8'h80&&wstrb[0])begin
     if(frame_active||input_fire||rs!=0||(s_axi_ctrl_arvalid&&s_axi_ctrl_arready&&!s_axi_ctrl_araddr[7]))bresp<=2;
     else begin isolated<=wdata[0];slot_reset<=wdata[1];if(isolated&&!wdata[0])generation<=generation+1'b1;end
    end else bresp<=2;
   end else if(isolated||slot_reset)begin bvalid<=1;bresp<=2;end
   else begin ws<=1;sent_aw<=0;sent_w<=0;end
  end
  if(ws==1)begin
   if(rp_s_axi_ctrl_awvalid&&rp_s_axi_ctrl_awready)sent_aw<=1;
   if(rp_s_axi_ctrl_wvalid&&rp_s_axi_ctrl_wready)sent_w<=1;
   if((sent_aw||rp_s_axi_ctrl_awready)&&(sent_w||rp_s_axi_ctrl_wready))ws<=2;
  end
  if(ws==2&&rp_s_axi_ctrl_bvalid)begin bvalid<=1;bresp<=rp_s_axi_ctrl_bresp;ws<=0;end
  if(s_axi_ctrl_arvalid&&s_axi_ctrl_arready)begin
   araddr<=s_axi_ctrl_araddr;rresp<=0;
   if(s_axi_ctrl_araddr[7])begin
    rvalid<=1;
    case(s_axi_ctrl_araddr)
     8'h80:rdata<={30'd0,slot_reset,isolated};
     8'h84:rdata<={29'd0,frame_active,slot_reset,isolated};
     8'h88:rdata<=isolated?32'hffffffff:module_id;
     8'h8c:rdata<=32'h44505231;
     8'h90:rdata<=generation;
     8'h94:rdata<=BUILD_TOKEN;
     8'h98:rdata<=module_id; // diagnostic raw ID; sample only after PCAP completion
     default:begin rdata<=0;rresp<=2;end
    endcase
   end else if(isolated||slot_reset)begin rvalid<=1;rdata<=0;rresp<=2;end
   else rs<=1;
  end
  if(rs==1&&rp_s_axi_ctrl_arready)rs<=2;
  if(rs==2&&rp_s_axi_ctrl_rvalid)begin rvalid<=1;rdata<=rp_s_axi_ctrl_rdata;rresp<=rp_s_axi_ctrl_rresp;rs<=0;end
 end
end
endmodule

`timescale 1ns/1ps
module tb_shell;
reg  aclk=0;
reg  aresetn=0;
reg [7:0] s_axi_ctrl_awaddr=0;
reg [2:0] s_axi_ctrl_awprot=0;
reg  s_axi_ctrl_awvalid=0;
wire  s_axi_ctrl_awready;
reg [31:0] s_axi_ctrl_wdata=0;
reg [3:0] s_axi_ctrl_wstrb=15;
reg  s_axi_ctrl_wvalid=0;
wire  s_axi_ctrl_wready;
wire [1:0] s_axi_ctrl_bresp;
wire  s_axi_ctrl_bvalid;
reg  s_axi_ctrl_bready=1;
reg [7:0] s_axi_ctrl_araddr=0;
reg [2:0] s_axi_ctrl_arprot=0;
reg  s_axi_ctrl_arvalid=0;
wire  s_axi_ctrl_arready;
wire [31:0] s_axi_ctrl_rdata;
wire [1:0] s_axi_ctrl_rresp;
wire  s_axi_ctrl_rvalid;
reg  s_axi_ctrl_rready=1;
reg [7:0] s_axis_tdata=0;
reg  s_axis_tvalid=0;
wire  s_axis_tready;
reg  s_axis_tlast=0;
wire [7:0] m_axis_tdata;
wire  m_axis_tvalid;
reg  m_axis_tready=1;
wire  m_axis_tlast;
wire [0:0] m_axis_tkeep;
always #5 aclk=~aclk;
dpr_shell dut(.aclk(aclk),.aresetn(aresetn),.s_axi_ctrl_awaddr(s_axi_ctrl_awaddr),.s_axi_ctrl_awprot(s_axi_ctrl_awprot),.s_axi_ctrl_awvalid(s_axi_ctrl_awvalid),.s_axi_ctrl_awready(s_axi_ctrl_awready),.s_axi_ctrl_wdata(s_axi_ctrl_wdata),.s_axi_ctrl_wstrb(s_axi_ctrl_wstrb),.s_axi_ctrl_wvalid(s_axi_ctrl_wvalid),.s_axi_ctrl_wready(s_axi_ctrl_wready),.s_axi_ctrl_bresp(s_axi_ctrl_bresp),.s_axi_ctrl_bvalid(s_axi_ctrl_bvalid),.s_axi_ctrl_bready(s_axi_ctrl_bready),.s_axi_ctrl_araddr(s_axi_ctrl_araddr),.s_axi_ctrl_arprot(s_axi_ctrl_arprot),.s_axi_ctrl_arvalid(s_axi_ctrl_arvalid),.s_axi_ctrl_arready(s_axi_ctrl_arready),.s_axi_ctrl_rdata(s_axi_ctrl_rdata),.s_axi_ctrl_rresp(s_axi_ctrl_rresp),.s_axi_ctrl_rvalid(s_axi_ctrl_rvalid),.s_axi_ctrl_rready(s_axi_ctrl_rready),.s_axis_tdata(s_axis_tdata),.s_axis_tvalid(s_axis_tvalid),.s_axis_tready(s_axis_tready),.s_axis_tlast(s_axis_tlast),.m_axis_tdata(m_axis_tdata),.m_axis_tvalid(m_axis_tvalid),.m_axis_tready(m_axis_tready),.m_axis_tlast(m_axis_tlast),.m_axis_tkeep(m_axis_tkeep));

task aw(input [7:0] a);begin
 @(negedge aclk);s_axi_ctrl_awaddr=a;s_axi_ctrl_awvalid=1;
 @(posedge aclk);while(!s_axi_ctrl_awready)@(posedge aclk);
 @(negedge aclk);s_axi_ctrl_awvalid=0;
end endtask
task wd(input [31:0] d);begin
 @(negedge aclk);s_axi_ctrl_wdata=d;s_axi_ctrl_wvalid=1;
 @(posedge aclk);while(!s_axi_ctrl_wready)@(posedge aclk);
 @(negedge aclk);s_axi_ctrl_wvalid=0;
end endtask
task write_split(input [7:0] a,input [31:0] d,input integer order,input [1:0] expected);begin
 if(order==0)begin aw(a);repeat(2)@(posedge aclk);wd(d);end
 else begin wd(d);repeat(2)@(posedge aclk);aw(a);end
 wait(s_axi_ctrl_bvalid);#1;
 if(s_axi_ctrl_bresp!==expected)$fatal(1,"BRESP %h expected %h",s_axi_ctrl_bresp,expected);
 @(negedge aclk);
end endtask
task read_check(input [7:0] a,input [31:0] d,input [1:0] expected);begin
 @(negedge aclk);s_axi_ctrl_araddr=a;s_axi_ctrl_arvalid=1;
 @(posedge aclk);while(!s_axi_ctrl_arready)@(posedge aclk);
 @(negedge aclk);s_axi_ctrl_arvalid=0;
 wait(s_axi_ctrl_rvalid);#1;
 if(s_axi_ctrl_rresp!==expected||s_axi_ctrl_rdata!==d)$fatal(1,"READ %h got %h resp %h expected %h/%h",a,s_axi_ctrl_rdata,s_axi_ctrl_rresp,d,expected);
 @(negedge aclk);
end endtask
task beat(input last);begin
 @(negedge aclk);s_axis_tvalid=1;s_axis_tlast=last;
 @(posedge aclk);while(!s_axis_tready)@(posedge aclk);
 @(negedge aclk);s_axis_tvalid=0;
end endtask
initial begin
 repeat(5)@(posedge aclk);@(negedge aclk);aresetn=1;
 read_check(8'h8c,32'h44505231,0);read_check(8'h80,3,0);
 read_check(8'h24,0,2);
 @(negedge aclk);s_axis_tvalid=1;#1;
 if(s_axis_tready!==0||m_axis_tvalid!==0)$fatal(1,"isolation did not block stream");
 @(negedge aclk);s_axis_tvalid=0;
 write_split(8'h80,0,0,0);read_check(8'h88,2,0);read_check(8'h90,1,0);
 write_split(8'h08,2,1,0);read_check(8'h24,32'h12345678,0);
 beat(0);read_check(8'h84,4,0);
 write_split(8'h80,3,0,2);read_check(8'h80,0,0);
 beat(1);read_check(8'h84,0,0);
 write_split(8'h80,3,1,0);read_check(8'h88,32'hffffffff,0);
 if(dut.rp.aresetn!==0)$fatal(1,"RP reset not held during isolation");
 dut.rp.identity=3;read_check(8'h88,32'hffffffff,0);read_check(8'h98,3,0);
 write_split(8'h80,0,0,0);read_check(8'h88,3,0);read_check(8'h90,2,0);
 write_split(8'h94,0,1,2);read_check(8'h94,1,0);
 $display("SHELL TEST PASSED: split AXI writes, forwarding, quiescence, isolation, reset, identity, generation");$finish;
end
initial begin #200000;$fatal(1,"shell test timeout");end
endmodule

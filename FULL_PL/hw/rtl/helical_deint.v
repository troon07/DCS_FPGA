// 24-row inverse permutation for the three supported LDACS coded lengths.
// Configuration is sampled BEFORE accepting the first input beat. No divider
// feeds the per-bit write-address recurrence. One bit per RAM location.
module helical_deint #(parameter MAX_BITS=29304)(
 input wire clk,rst,input wire [15:0] cfg_bits,
 input wire s_valid,output wire s_ready,input wire s_bit,
 output wire m_valid,input wire m_ready,output wire m_bit
);
 localparam PREP=0,LOAD=1,WAIT_READ=2,OUTPUT=3;
 reg [1:0] state;
 (* ram_style="block" *) reg mem[0:MAX_BITS-1];
 reg q;
 reg [14:0] count,base,addr,n_bits;
 reg [10:0] cols,col,t;
 reg [4:0] row;
 wire [14:0] write_addr=base+{4'd0,col};
 assign s_ready=state==LOAD;
 assign m_valid=state==OUTPUT;
 assign m_bit=q;
 always @(posedge clk)begin
  if(s_valid&&s_ready)mem[write_addr]<=s_bit;
  q<=mem[addr];
 end
 always @(posedge clk)begin
  if(rst)begin state<=PREP;count<=0;base<=0;col<=0;t<=0;addr<=0;row<=0;cols<=0;n_bits<=0;end
  else case(state)
   PREP:if(s_valid)begin
    count<=0;base<=0;col<=0;t<=0;addr<=0;row<=0;
    // Host/firmware already reject unsupported lengths; keep READY low for
    // invalid direct RTL configurations rather than writing beyond the RAM.
    if(cfg_bits<=MAX_BITS)case(cfg_bits)
     16'd9768:begin cols<=11'd407;n_bits<=15'd9768;state<=LOAD;end
     16'd19536:begin cols<=11'd814;n_bits<=15'd19536;state<=LOAD;end
     16'd29304:begin cols<=11'd1221;n_bits<=15'd29304;state<=LOAD;end
     default:state<=PREP;
    endcase
   end
   LOAD:if(s_valid)begin
    count<=count+1'b1;
    if(row==23)begin row<=0;base<=0;t<=t+1'b1;col<=t+1'b1;end
    else begin row<=row+1'b1;base<=base+{4'd0,cols};col<=(col==cols-1'b1)?11'd0:col+1'b1;end
    if(count==n_bits-1'b1)begin addr<=0;state<=WAIT_READ;end
   end
   WAIT_READ:state<=OUTPUT;
   OUTPUT:if(m_ready)begin
    if(addr==n_bits-1'b1)begin state<=PREP;count<=0;base<=0;col<=0;t<=0;row<=0;addr<=0;end
    else begin addr<=addr+1'b1;state<=WAIT_READ;end
   end
   default:state<=PREP;
  endcase
 end
endmodule

// The same 24-row inverse permutation as sw/src/helical.c.
// A coded bit occupies ONE memory bit (not a UART byte). One frame buffered.
module helical_deint #(parameter MAX_BITS=29304)(
    input wire clk,rst,
    input wire [15:0] cfg_bits,
    input wire s_valid, output wire s_ready,input wire s_bit,
    output wire m_valid,input wire m_ready,output wire m_bit
);
    localparam LOAD=0,WAIT_READ=1,OUTPUT=2;
    reg [1:0] state;
    (* ram_style="block" *) reg mem[0:MAX_BITS-1];
    reg q;
    reg [15:0] count,base,col,t,addr;
    reg [4:0] row;
    wire [15:0] cols=cfg_bits/24;
    wire [15:0] write_addr=base+col;
    assign s_ready=state==LOAD;
    assign m_valid=state==OUTPUT;
    assign m_bit=q;
    always @(posedge clk) begin
        if(s_valid&&s_ready)mem[write_addr]<=s_bit;
        q<=mem[addr];
    end
    always @(posedge clk) begin
        if(rst)begin state<=LOAD;count<=0;base<=0;col<=0;t<=0;addr<=0;row<=0;end
        else case(state)
        LOAD:if(s_valid)begin
            count<=count+1'b1;
            if(row==23)begin row<=0;base<=0;t<=t+1'b1;col<=t+1'b1;end
            else begin row<=row+1'b1;base<=base+cols;col<=(col==cols-1)?16'd0:col+1'b1;end
            if(count==cfg_bits-1)begin addr<=0;state<=WAIT_READ;end
        end
        WAIT_READ:state<=OUTPUT;
        OUTPUT:if(m_ready)begin
            if(addr==cfg_bits-1)begin
                state<=LOAD;count<=0;base<=0;col<=0;t<=0;row<=0;addr<=0;
            end else begin addr<=addr+1'b1;state<=WAIT_READ;end
        end
        default:state<=LOAD;
        endcase
    end
endmodule

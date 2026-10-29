// MSB-first byte XOR with x^15+x^14+1, seed 0x4a80, matching the baseline.
// State advances only on accepted bytes and restarts at each frame boundary.
module prbs_derand(
    input wire clk,rst,input wire [15:0] cfg_bytes,
    input wire [7:0] s_data,input wire s_valid,output wire s_ready,
    output wire [7:0] m_data,output wire m_valid,input wire m_ready
);
    reg [14:0] lfsr,next_lfsr;
    reg [15:0] count;
    reg [7:0] mask;
    integer i;
    always @* begin
        next_lfsr=lfsr;mask=0;
        for(i=0;i<8;i=i+1)begin
            mask={mask[6:0],next_lfsr[14]^next_lfsr[13]};
            next_lfsr={next_lfsr[13:0],next_lfsr[14]^next_lfsr[13]};
        end
    end
    assign s_ready=m_ready;
    assign m_valid=s_valid;
    assign m_data=s_data^mask;
    always @(posedge clk) begin
        if(rst)begin lfsr<=15'h4a80;count<=0;end
        else if(s_valid&&s_ready)begin
            if(count==cfg_bytes-1)begin lfsr<=15'h4a80;count<=0;end
            else begin lfsr<=next_lfsr;count<=count+1'b1;end
        end
    end
endmodule

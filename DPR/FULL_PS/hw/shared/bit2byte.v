// ============================================================================
// bit2byte.v - packs a bit stream into bytes, MSB first
// ============================================================================
module bit2byte (
    input  wire       clk,
    input  wire       rst,
    input  wire       s_valid,
    output wire       s_ready,
    input  wire       s_bit,
    output wire       m_valid,
    input  wire       m_ready,
    output wire [7:0] m_data
);
    reg [2:0] cnt;
    reg [7:0] sh;
    reg       full;
    assign s_ready = !full;
    assign m_valid = full;
    assign m_data  = sh;
    always @(posedge clk) begin
        if (rst) begin
            cnt <= 0; sh <= 0; full <= 0;
        end else begin
            if (full && m_ready) full <= 1'b0;
            if (s_valid && !full) begin
                sh  <= {sh[6:0], s_bit};
                cnt <= cnt + 3'd1;
                if (cnt == 3'd7) full <= 1'b1;
            end
        end
    end
endmodule

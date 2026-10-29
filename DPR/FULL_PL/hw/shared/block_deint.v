// ============================================================================
// block_deint.v - LDACS block (byte) deinterleaver
// Interleaver (TX): byte j of the interleaved frame = codeword (j mod d), byte (j div d)
// Deinterleaver   : outputs codeword 0 bytes 0..N-1, then codeword 1, ...
// Kept in the FPGA (as in the paper) so data stays in hardware between
// the Viterbi and Reed-Solomon decoders (no extra DMA transfers).
// Must match model/ldacs_ref.py:block_deinterleave()
// ============================================================================
module block_deint #(
    parameter MAX_BYTES = 4096,
    parameter AW        = 12
)(
    input  wire          clk,
    input  wire          rst,
    input  wire [7:0]    cfg_num_cw,    // d  (number of RS codewords)
    input  wire [7:0]    cfg_rs_n,      // N  (bytes per codeword)
    input  wire          s_valid,
    output wire          s_ready,
    input  wire [7:0]    s_data,
    output wire          m_valid,
    input  wire          m_ready,
    output wire [7:0]    m_data
);
    localparam S_LOAD = 2'd0, S_RDW = 2'd1, S_OUT = 2'd2;
    reg [1:0]    state;
    reg [AW-1:0] wa, total, addr;
    reg [7:0]    d, n, cw, p;
    reg [7:0]    mem [0:MAX_BYTES-1];
    reg [7:0]    rd;

    wire [15:0] prod = cfg_num_cw * cfg_rs_n;
    assign s_ready = (state == S_LOAD);
    assign m_valid = (state == S_OUT);
    assign m_data  = rd;

    always @(posedge clk) begin
        if (state == S_LOAD && s_valid) mem[wa] <= s_data;
        rd <= mem[addr];
    end

    always @(posedge clk) begin
        if (rst) begin
            state <= S_LOAD; wa <= 0; addr <= 0; cw <= 0; p <= 0;
        end else case (state)
            S_LOAD: if (s_valid) begin
                if (wa == 0) begin
                    total <= prod[AW-1:0];
                    d     <= cfg_num_cw;
                    n     <= cfg_rs_n;
                end
                if (wa != 0 && wa == total - 1'b1) begin
                    wa <= 0; cw <= 0; p <= 0; addr <= 0;
                    state <= S_RDW;
                end else
                    wa <= wa + 1'b1;
            end
            S_RDW: state <= S_OUT;
            S_OUT: if (m_ready) begin
                state <= S_RDW;
                if (p == n - 1'b1) begin
                    p <= 0;
                    if (cw == d - 1'b1)
                        state <= S_LOAD;
                    else begin
                        cw   <= cw + 1'b1;
                        addr <= cw + 1'b1;
                    end
                end else begin
                    p    <= p + 1'b1;
                    addr <= addr + d;
                end
            end
            default: state <= S_LOAD;
        endcase
    end
endmodule

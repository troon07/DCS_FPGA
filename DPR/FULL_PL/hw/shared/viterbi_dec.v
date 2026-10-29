// ============================================================================
// viterbi_dec.v - LDACS convolutional (Viterbi) decoder, K=7, G=(171,133) octal
//
// * Input : punctured coded bit stream, one bit per handshake (hard decision)
// * Output: decoded info bits (first cfg_n_out bits of the frame)
// * Depuncturing built in: rate 0=1/2, 1=2/3, 2=3/4 (missing bits = erasures)
// * Frame based: all trellis steps are processed, decisions stored in block
//   RAM, then one traceback from state 0 (encoder terminated with 6 zero bits).
//
// Throughput: ~3 clock cycles per step forward + 2 per step traceback + output.
// At 100 MHz a 64QAM-3/4 frame (21978 steps) takes ~2.2 ms.
//
// Memory: MAX_STEPS x 64 bits of decisions. It is explicitly banked as
// 512x64 blocks so Vivado uses the native 512x72 RAMB36 geometry instead of
// mapping each decision bit to a separate deep RAM.
// Must match model/ldacs_ref.py:viterbi_decode()
// ============================================================================
module viterbi_dec #(
    parameter MAX_STEPS = 22016,
    parameter AW        = 15
)(
    input  wire          clk,
    input  wire          rst,
    // configuration (latched at frame start)
    input  wire [1:0]    cfg_rate,
    input  wire [AW-1:0] cfg_n_steps,   // trellis steps incl. tail bits
    input  wire [AW-1:0] cfg_n_out,     // number of decoded bits to output
    // coded bit input
    input  wire          s_valid,
    output reg           s_ready,
    input  wire          s_bit,
    // decoded bit output
    output reg           m_valid,
    input  wire          m_ready,
    output wire          m_bit,
    output wire          busy
);
    localparam S_IDLE = 4'd0, S_GETX = 4'd1, S_GETY = 4'd2, S_ACS = 4'd3,
               S_TBW  = 4'd4, S_TB   = 4'd5, S_OUTW = 4'd6, S_OUT = 4'd7;

    reg [3:0]    state;
    reg [1:0]    rate;
    reg [AW-1:0] n_steps, n_out, step, tb_k, ok;
    reg [1:0]    phase;
    reg          r1, e1, r2, e2;
    reg [5:0]    tb_state;
    reg [8*64-1:0] pm;          // path metrics, 8 bit modulo arithmetic

    assign busy = (state != S_IDLE);

    // ---------------- puncturing pattern ----------------
    reg need_x, need_y, last_phase;
    always @* begin
        need_x = 1'b1; need_y = 1'b1; last_phase = 1'b1;
        case (rate)
            2'd1: begin // 2/3 : X=10 Y=11
                need_x     = (phase == 2'd0);
                last_phase = (phase == 2'd1);
            end
            2'd2: begin // 3/4 : X=101 Y=110
                need_x     = (phase != 2'd1);
                need_y     = (phase != 2'd2);
                last_phase = (phase == 2'd2);
            end
            default: ;
        endcase
    end

    // ---------------- add-compare-select (64 states in parallel) ----------------
    wire [8*64-1:0] pm_new;
    wire [63:0]     dec_w;
    genvar g;
    generate
        for (g = 0; g < 64; g = g + 1) begin : acs
            localparam integer PS0 = (g % 32) * 2;     // predecessor with b=0
            localparam integer PS1 = (g % 32) * 2 + 1; // predecessor with b=1
            wire [5:0] ns   = g;
            wire [6:0] reg0 = {ns, 1'b0};
            wire [6:0] reg1 = {ns, 1'b1};
            wire c1_0 = ^(reg0 & 7'o171);
            wire c2_0 = ^(reg0 & 7'o133);
            wire c1_1 = ^(reg1 & 7'o171);
            wire c2_1 = ^(reg1 & 7'o133);
            wire [7:0] bm0 = {7'd0, e1 & (r1 ^ c1_0)} + {7'd0, e2 & (r2 ^ c2_0)};
            wire [7:0] bm1 = {7'd0, e1 & (r1 ^ c1_1)} + {7'd0, e2 & (r2 ^ c2_1)};
            wire [7:0] m0  = pm[PS0*8 +: 8] + bm0;
            wire [7:0] m1  = pm[PS1*8 +: 8] + bm1;
            wire [7:0] diff = m0 - m1;
            wire sel = (diff != 8'd0) && !diff[7];      // m1 < m0 (modulo compare)
            assign pm_new[g*8 +: 8] = sel ? m1 : m0;
            assign dec_w[g] = sel;
        end
    endgenerate

    // ---------------- memories (inferred block RAM) ----------------
    // A monolithic 22016x64 declaration is inferred as 64 deep/narrow RAMB36
    // blocks on 7-series devices. Banking at 512 entries permits one RAMB36
    // per 64-bit bank and keeps the largest mode within XC7Z010 capacity.
    localparam DEC_BANK_AW = 9;
    localparam DEC_BANK_DEPTH = (1 << DEC_BANK_AW);
    localparam DEC_BANKS = (MAX_STEPS + DEC_BANK_DEPTH - 1) / DEC_BANK_DEPTH;
    wire [63:0] dec_bank_rd [0:DEC_BANKS-1];
    wire [AW-DEC_BANK_AW-1:0] step_bank = step[AW-1:DEC_BANK_AW];
    wire [AW-DEC_BANK_AW-1:0] tb_bank = tb_k[AW-1:DEC_BANK_AW];
    genvar db;
    generate
        for (db = 0; db < DEC_BANKS; db = db + 1) begin : decision_banks
            (* ram_style = "block" *) reg [63:0] mem [0:DEC_BANK_DEPTH-1];
            reg [63:0] q;
            always @(posedge clk) begin
                if (state == S_ACS && step_bank == db)
                    mem[step[DEC_BANK_AW-1:0]] <= dec_w;
                q <= mem[tb_k[DEC_BANK_AW-1:0]];
            end
            assign dec_bank_rd[db] = q;
        end
    endgenerate

    reg [63:0] dec_rd;
    integer db_sel;
    always @* begin
        dec_rd = 64'd0;
        for (db_sel = 0; db_sel < DEC_BANKS; db_sel = db_sel + 1)
            if (tb_bank == db_sel)
                dec_rd = dec_bank_rd[db_sel];
    end

    reg        out_mem [0:MAX_STEPS-1];
    reg        out_rd;

    always @(posedge clk) begin
        if (state == S_TB) out_mem[tb_k] <= tb_state[5];
        out_rd <= out_mem[ok];
    end
    assign m_bit = out_rd;

    // ---------------- control FSM ----------------
    integer i;
    always @* begin
        s_ready = 1'b0;
        m_valid = 1'b0;
        case (state)
            S_GETX: s_ready = need_x;
            S_GETY: s_ready = need_y;
            S_OUT : m_valid = 1'b1;
            default: ;
        endcase
    end

    always @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            step <= 0; tb_k <= 0; ok <= 0; phase <= 0;
            r1 <= 0; e1 <= 0; r2 <= 0; e2 <= 0; tb_state <= 0;
        end else begin
            case (state)
            S_IDLE: if (s_valid) begin
                rate    <= cfg_rate;
                n_steps <= cfg_n_steps;
                n_out   <= cfg_n_out;
                step    <= 0;
                phase   <= 0;
                for (i = 0; i < 64; i = i + 1)
                    pm[i*8 +: 8] <= (i == 0) ? 8'd0 : 8'd32;
                state <= S_GETX;
            end
            S_GETX: begin
                if (!need_x) begin
                    r1 <= 1'b0; e1 <= 1'b0; state <= S_GETY;
                end else if (s_valid) begin
                    r1 <= s_bit; e1 <= 1'b1; state <= S_GETY;
                end
            end
            S_GETY: begin
                if (!need_y) begin
                    r2 <= 1'b0; e2 <= 1'b0; state <= S_ACS;
                end else if (s_valid) begin
                    r2 <= s_bit; e2 <= 1'b1; state <= S_ACS;
                end
            end
            S_ACS: begin
                pm    <= pm_new;
                phase <= last_phase ? 2'd0 : phase + 2'd1;
                step  <= step + 1'b1;
                if (step == n_steps - 1'b1) begin
                    tb_k     <= n_steps - 1'b1;
                    tb_state <= 6'd0;           // terminated trellis
                    state    <= S_TBW;
                end else
                    state <= S_GETX;
            end
            S_TBW: state <= S_TB;               // wait for dec_rd
            S_TB: begin
                tb_state <= {tb_state[4:0], dec_rd[tb_state]};
                if (tb_k == 0) begin
                    ok    <= 0;
                    state <= S_OUTW;
                end else begin
                    tb_k  <= tb_k - 1'b1;
                    state <= S_TBW;
                end
            end
            S_OUTW: state <= S_OUT;             // wait for out_rd
            S_OUT: if (m_ready) begin
                if (ok == n_out - 1'b1)
                    state <= S_IDLE;
                else begin
                    ok    <= ok + 1'b1;
                    state <= S_OUTW;
                end
            end
            default: state <= S_IDLE;
            endcase
        end
    end
endmodule

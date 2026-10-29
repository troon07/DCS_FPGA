#!/usr/bin/env python3
"""
LDACS Web Frontend Server
Serves TX & RX cockpits. Hardware path: PC -> COM5 -> FPGA -> COM5 -> PC.
Paper: Kurz et al., IEEE OJIES 2022.
"""

import http.server
import socketserver
import json
import os
import sys
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from model.ldacs_engine import engine_instance, load_vivado_build_metrics

PORT    = 8000
WEB_DIR = os.path.join(BASE_DIR, "web")


class LDACSHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def log_message(self, fmt, *args):
        pass   # suppress per-request noise; errors still appear

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        p = url.path

        if p in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/tx/index.html")
            self.end_headers()
            return

        routes = {
            "/api/status":      self._api_status,
            "/api/last_result": self._api_last_result,
            "/api/hw/status":   self._api_hw_status,
        }
        if p in routes:
            routes[p]()
        else:
            super().do_GET()

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        p = url.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        routes = {
            "/api/tx/transmit":  lambda: self._api_transmit(data),
            "/api/tx/generate":  lambda: self._api_transmit(data),
            "/api/hw/boot":      self._api_hw_boot,
        }
        if p in routes:
            routes[p]()
        else:
            self.send_error(404, f"Unknown endpoint: {p}")

    # ── API handlers ───────────────────────────────────────────────────────

    def _api_status(self):
        last = engine_instance.last_result
        hw   = last["hw_active"] if last else engine_instance.hw_connected
        routed = load_vivado_build_metrics(BASE_DIR).get("total") or {}
        self.send_json({
            "status": "connected" if hw else "hardware_not_verified",
            "hw_active": hw,
            "hw_mode_desc": last["hw_mode_desc"] if last else "No hardware transaction has completed.",
            "device": "xc7z010clg400-1",
            "com_port": "COM5",
            "baud": 115200,
            "clock_mhz": 71.429,
            # Parsed from the current routed report; never a paper/reference value.
            "utilization": {
                "lut_used": routed.get("lut"),
                "ff_used": routed.get("ff"),
                "bram_used": routed.get("bram"),
                "dsp_used": routed.get("dsp"),
                "source": "Current Vivado routed XC7Z010 implementation report",
            },
            "last_measured": {
                "throughput_mbps": last.get("throughput_mbps") if last else None,
                "latency_ms":      last.get("latency_ms") if last else None,
                "residual_ber":    last.get("residual_ber") if last else None,
                "is_bit_exact":    last.get("is_bit_exact") if last else None,
            },
        })

    def _api_last_result(self):
        if engine_instance.last_result:
            self.send_json(engine_instance.last_result)
        else:
            self.send_json({"status": "no_hardware_result", "hw_active": False,
                            "message": "No message has been accepted from FPGA hardware yet."})

    def _api_transmit(self, data):
        payload    = data.get("payload", "Hello LDACS")
        mode       = data.get("mode", "qpsk_1_2")
        self.send_json(engine_instance.process_transmission(payload, mode=mode))

    def _api_hw_status(self):
        self.send_json(engine_instance.get_hw_status())

    def _api_hw_boot(self):
        """Programs bitstream + loads uart_bridge.elf + starts ARM core."""
        result = engine_instance.boot_board()
        self.send_json(result)

    # ── Helpers ────────────────────────────────────────────────────────────

    def send_json(self, data):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    print("=" * 72)
    print("  LDACS TRANSCEIVER — REAL HARDWARE EDITION")
    print("  Paper: Kurz et al., IEEE OJIES 2022")
    print(f"  TX Cockpit : http://localhost:{PORT}/tx/index.html")
    print(f"  RX Cockpit : http://localhost:{PORT}/rx/index.html")
    print("  Hardware   : configured COM port (UART) -> EDGE Z7-10 / Zynq xc7z010 FPGA")
    print("  Boot FPGA  : POST /api/hw/boot  (powers up uart_bridge firmware)")
    print("=" * 72)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), LDACSHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")

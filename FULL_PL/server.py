#!/usr/bin/env python3
"""Local console for actual board traces and one-pass benchmark batches."""
import argparse,http.server,json,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'host'))
import board_client as client
lock=threading.Lock()
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/','/index.html'):self.send_error(404);return
        body=(ROOT/'web/index.html').read_bytes().replace(b'VARIANT_NAME',client.ARCH_NAMES[client.ARCHITECTURE].encode())
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(body)
    def do_POST(self):
        if self.path not in ('/api/trace','/api/benchmark'):self.send_error(404);return
        length=int(self.headers.get('Content-Length','0'))
        if length>65536:self.send_error(413);return
        try:
            data=json.loads(self.rfile.read(length));mode=data.get('mode','qpsk_1_2')
            with lock:
                board=client.Board(self.server.serial_port)
                try:
                    if self.path=='/api/trace':
                        lay,payload,tx=client.prepare(mode,text=data.get('message','LDACS RESEARCH'))
                        result=board.trace(lay,payload,tx)
                    else:
                        result=client.collect(board,[mode],int(data.get('iterations',20)),2,1)
                finally:board.close()
            response={'ok':True,'result':result}
        except Exception as error:response={'ok':False,'error':str(error)}
        body=json.dumps(response).encode();self.send_response(200);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',default='COM5');p.add_argument('--http-port',type=int,default=8001);a=p.parse_args()
    with http.server.ThreadingHTTPServer(('127.0.0.1',a.http_port),Handler) as server:
        server.serial_port=a.port
        print(f'{client.ARCH_NAMES[client.ARCHITECTURE]} console: http://127.0.0.1:{a.http_port} (UART {a.port})')
        server.serve_forever()

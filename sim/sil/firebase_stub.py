"""Local HTTP server that accepts the PUT requests `gateway/firebase_bridge.py` sends to Firebase, and records their arrival times.
It stands in for the Firebase Realtime Database; it checks nothing about Firebase itself."""
from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FirebaseStub:
    def __init__(self):
        self.puts: list = []                       # (time.monotonic(), path)
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_PUT(self):
                n = int(self.headers.get("Content-Length", 0)); self.rfile.read(n)
                outer.puts.append((time.monotonic(), self.path.split("?")[0]))
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown(); self.server.server_close()

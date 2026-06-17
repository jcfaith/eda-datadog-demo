#!/usr/bin/env python3
"""
Kill service sidecar — listens on port 8080, proxied through nginx at /kill.
Receives the POST from the demo kill button and stops nginx via systemd.
Stays alive after nginx stops (it's a separate process) but becomes unreachable
from outside since nginx is the only thing exposing it publicly.
"""

import subprocess
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("kill-service")

KILL_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8"/>
  <title>Killing app...</title>
  <style>
    body { background:#0f1117; color:#e2e8f0; font-family:system-ui,sans-serif;
           display:flex; align-items:center; justify-content:center; height:100vh; }
    .box { text-align:center; }
    h1 { color:#ef4444; font-size:2rem; }
    p  { color:#94a3b8; margin-top:1rem; }
  </style>
</head>
<body>
  <div class="box">
    <h1>&#128165; App killed.</h1>
    <p>nginx is stopping. Watch Datadog for the alert...</p>
  </div>
</body>
</html>"""


class KillHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.info(fmt % args)

    def do_GET(self):
        if self.path == "/healthz":
            self._respond(200, b"ok")
        else:
            self._respond(404, b"not found")

    def do_POST(self):
        if self.path == "/kill":
            log.warning("KILL request received — stopping nginx")
            self._respond(200, KILL_HTML.encode())
            # Stop nginx after the response is flushed
            subprocess.Popen(
                ["sudo", "systemctl", "stop", "nginx"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            self._respond(404, b"not found")

    def _respond(self, code, body, content_type="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8080), KillHandler)
    log.info("Kill service listening on 127.0.0.1:8080")
    server.serve_forever()

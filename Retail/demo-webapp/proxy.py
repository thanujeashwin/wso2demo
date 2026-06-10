"""Local CORS proxy — forwards /chat to the WSO2 Agent Manager gateway."""
import http.server, urllib.request, urllib.error, json, sys

GATEWAY = "http://default-default.openchoreoapis.localhost:19080/customer-agent-customer-agent-endpoint"
PORT    = 8010

class Proxy(http.server.BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        target = GATEWAY + self.path
        req    = urllib.request.Request(
            target, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
                self.send_response(resp.status)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

if __name__ == "__main__":
    print(f"CORS proxy → {GATEWAY}")
    print(f"Listening on http://localhost:{PORT}")
    http.server.HTTPServer(("", PORT), Proxy).serve_forever()

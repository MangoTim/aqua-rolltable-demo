"""Serve lunch-roulette.html at the root, plus _tools/ as static files.

Replaces the bare `python -m http.server 8082` so visiting
http://localhost:8082/ opens the lunch roulette wheel directly
instead of a directory listing.

Container note: bind to 0.0.0.0 (via HOST env var) so the server is
reachable from outside the container, not just loopback.
"""
from http.server import HTTPServer, SimpleHTTPRequestHandler
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = "lunch-roulette.html"


class LunchHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.path = "/" + INDEX
        return super().do_GET()

    def log_message(self, fmt, *args):
        # Quieter logs (one line per request)
        sys.stderr.write("[8082] %s\n" % (fmt % args))


def main():
    os.chdir(ROOT)
    port = int(os.environ.get("PORT", "8082"))
    # Default to 0.0.0.0 so this works both in containers (set HOST=0.0.0.0)
    # and on the host (set HOST=127.0.0.1 for loopback-only dev).
    host = os.environ.get("HOST", "0.0.0.0")
    httpd = HTTPServer((host, port), LunchHandler)
    print(f"Serving {ROOT} on http://{host}:{port}/  (root -> {INDEX})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()

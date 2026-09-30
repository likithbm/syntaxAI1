"""Local development server: runs the exact Lambda handler behind a plain HTTP server.

    python local_server.py            # http://localhost:8000
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent


def load_env(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env(HERE / ".env")
load_env(HERE.parent / ".env")
sys.path.insert(0, str(HERE))

from app.handler import lambda_handler  # noqa: E402


class H(BaseHTTPRequestHandler):
    def _run(self):
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        event = {"requestContext": {"http": {"method": self.command}}, "rawPath": self.path.split("?")[0], "body": body}
        res = lambda_handler(event, None)
        data = res["body"].encode("utf-8")
        self.send_response(res["statusCode"])
        for k, v in res["headers"].items():
            self.send_header(k, v)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_OPTIONS = _run

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Syntax AI API on http://localhost:{port}  (Bedrock model: {os.environ.get('BEDROCK_MODEL_ID') or 'NOT SET'}"
          f"{', fixture mode' if os.environ.get('ANALYSIS_FIXTURE') else ''})")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()

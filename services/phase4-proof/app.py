"""Minimal private Cloud Run proof service for Resilio Phase 4."""
from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def source_sha() -> str:
    value = os.environ.get("SOURCE_SHA", "")
    if not FULL_SHA.fullmatch(value):
        raise RuntimeError("SOURCE_SHA must be an exact Git commit SHA")
    return value


def health_payload() -> bytes:
    return json.dumps(
        {"status": "ok", "source_sha": source_sha()},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/healthz":
            self.send_response(404)
            self.end_headers()
            return
        body = health_payload()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()

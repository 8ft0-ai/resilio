from __future__ import annotations
import json
import os
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import patch

import app


class ProofServiceTests(unittest.TestCase):
    def test_health_payload_binds_source(self) -> None:
        with patch.dict(os.environ, {"SOURCE_SHA": "a" * 40}, clear=False):
            self.assertEqual(
                app.health_payload(),
                b'{"source_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","status":"ok"}',
            )

    def test_missing_or_malformed_source_fails(self) -> None:
        for value in ("", "main", "A" * 40, "a" * 39):
            with self.subTest(value=value), patch.dict(
                os.environ, {"SOURCE_SHA": value}, clear=False
            ):
                with self.assertRaises(RuntimeError):
                    app.source_sha()

    def test_http_contract_uses_non_reserved_health_path(self) -> None:
        with patch.dict(os.environ, {"SOURCE_SHA": "b" * 40}, clear=False):
            server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with urlopen(base + "/health", timeout=2) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(
                        json.loads(response.read()),
                        {"status": "ok", "source_sha": "b" * 40},
                    )
                with self.assertRaises(HTTPError) as stopped:
                    urlopen(base + "/healthz", timeout=2)
                self.assertEqual(stopped.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()

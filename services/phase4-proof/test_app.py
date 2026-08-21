from __future__ import annotations
import os
import unittest
from unittest.mock import patch
import app


class ProofServiceTests(unittest.TestCase):
    def test_health_payload_binds_source(self) -> None:
        with patch.dict(os.environ, {"SOURCE_SHA": "a" * 40}, clear=False):
            self.assertEqual(app.health_payload(), b'{"source_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","status":"ok"}')

    def test_missing_or_malformed_source_fails(self) -> None:
        for value in ("", "main", "A" * 40, "a" * 39):
            with self.subTest(value=value), patch.dict(os.environ, {"SOURCE_SHA": value}, clear=False):
                with self.assertRaises(RuntimeError):
                    app.source_sha()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase4_supply_chain as p4  # noqa: E402


class Phase4ScanV1RegressionTests(unittest.TestCase):
    def test_finished_v1_discovery_accepts_ecosystem_analysis_types(self) -> None:
        discovery = {
            "occurrences": [{
                "discovery": {
                    "analysisStatus": "FINISHED_SUCCESS",
                    "analysisCompleted": {
                        "analysisType": [
                            "NPM", "OS", "COMPOSER", "PYPI", "RUST",
                            "MAVEN", "RUBYGEMS", "NUGET", "GO", "SECRET",
                        ]
                    },
                }
            }]
        }
        high = {"occurrences": [{"vulnerability": {"effectiveSeverity": "HIGH"}}]}
        self.assertEqual(p4.scan_disposition(discovery, high), "HIGH_REVIEW_REQUIRED")

    def test_non_finished_v1_discovery_remains_fail_closed(self) -> None:
        discovery = {
            "occurrences": [{
                "discovery": {
                    "analysisStatus": "SCANNING",
                    "analysisCompleted": {"analysisType": ["OS"]},
                }
            }]
        }
        with self.assertRaisesRegex(p4.SupplyChainError, "VULNERABILITY_SCAN_UNAVAILABLE"):
            p4.scan_disposition(discovery, {"occurrences": []})


if __name__ == "__main__":
    unittest.main()

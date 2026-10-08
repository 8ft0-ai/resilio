"""Regression tests for the credential-free connected Phase 5 demonstration."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.phase5_demo import demonstrate


class Phase5DemoTests(unittest.TestCase):
    def test_connected_product_demonstration(self):
        transcript = demonstrate()
        self.assertEqual(transcript["result"], "PASS")
        self.assertEqual(transcript["scope"], "LOCAL_FAKE_PROVIDER_ONLY")
        self.assertIs(transcript["live_provider_acceptance"], False)
        self.assertEqual(transcript["final_stored_count"], 1)
        self.assertEqual(transcript["final_rejection_count"], 2)
        self.assertNotEqual(transcript["first_message_id"],
                            transcript["replay_message_id"])
        steps = {row["phase"]: row for row in transcript["steps"]}
        self.assertEqual(steps["before"]["http_status"], 404)
        self.assertEqual(steps["ingest"]["http_status"], 202)
        self.assertEqual(steps["process"]["response"]["status"], "acknowledged")
        self.assertEqual(steps["read"]["response"]["first_pubsub_message_id"],
                         transcript["first_message_id"])
        self.assertEqual(steps["replay_process"]["response"]["status"], "acknowledged")
        self.assertEqual(steps["replay_read"]["response"]["first_pubsub_message_id"],
                         transcript["first_message_id"])
        self.assertEqual(steps["conflict_process"]["response"]["status"], "rejected")
        self.assertEqual(steps["invalid_ingest"]["http_status"], 400)
        self.assertEqual(steps["invalid_push"]["response"]["status"], "rejected")
        self.assertEqual(steps["rejection_store_failure"]["http_status"], 503)
        self.assertEqual(steps["api_write_forbidden"]["http_status"], 404)
        self.assertTrue(all(row["assertion"] == "PASS" for row in transcript["steps"]))

    def test_deterministic_transcript(self):
        first = demonstrate()
        second = demonstrate()
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))


if __name__ == "__main__":
    unittest.main()

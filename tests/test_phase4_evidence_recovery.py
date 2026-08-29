from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase4_evidence_recovery as recovery  # noqa: E402


class Phase4EvidenceRecoveryTests(unittest.TestCase):
    def test_current_main_build_remains_eligible(self) -> None:
        source = "a" * 40
        self.assertEqual(
            recovery.require_source_eligibility(
                "12345678-abcd",
                source,
                "b" * 40,
                source,
            ),
            "CURRENT_MAIN",
        )

    def test_only_exact_preserved_tuple_bypasses_stale_main(self) -> None:
        self.assertEqual(
            recovery.require_source_eligibility(
                recovery.PRESERVED_RECOVERY_BUILD_ID,
                recovery.PRESERVED_RECOVERY_SOURCE_SHA,
                recovery.PRESERVED_RECOVERY_BUILD_CONTROL_SHA,
                "f" * 40,
            ),
            "PRESERVED_RECOVERY",
        )

        mutations = (
            ("build_id", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
            ("source_sha", "a" * 40),
            ("build_control_sha", "b" * 40),
        )
        for field, value in mutations:
            args = {
                "build_id": recovery.PRESERVED_RECOVERY_BUILD_ID,
                "source_sha": recovery.PRESERVED_RECOVERY_SOURCE_SHA,
                "build_control_sha": recovery.PRESERVED_RECOVERY_BUILD_CONTROL_SHA,
                "current_main_sha": "f" * 40,
            }
            args[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                recovery.EvidenceRecoveryError,
                "STALE_BUILD_NOT_AUTHORISED",
            ):
                recovery.require_source_eligibility(**args)

    def test_malformed_identity_fails_closed(self) -> None:
        with self.assertRaisesRegex(recovery.EvidenceRecoveryError, "BUILD_ID_INVALID"):
            recovery.require_source_eligibility("bad", "a" * 40, "b" * 40, "a" * 40)
        with self.assertRaisesRegex(recovery.EvidenceRecoveryError, "SOURCE_SHA_INVALID"):
            recovery.require_source_eligibility("12345678-abcd", "bad", "b" * 40, "a" * 40)

    def test_workflow_uses_helper_and_has_no_direct_stale_main_bypass(self) -> None:
        workflow = (ROOT / ".github/workflows/phase4-evidence-reusable.yml").read_text(encoding="utf-8")
        invocation = "python3 scripts/phase4_evidence_recovery.py"
        self.assertEqual(workflow.count(invocation), 1)
        self.assertNotIn('test "$CURRENT" = "$SOURCE_SHA"', workflow)
        for argument in (
            '--build-id "$BUILD_ID"',
            '--source-sha "$SOURCE_SHA"',
            '--build-control-sha "$WORKFLOW_SHA"',
            '--current-main-sha "$CURRENT"',
        ):
            self.assertIn(argument, workflow)

    def test_recovery_constants_are_exact_governed_tuple(self) -> None:
        self.assertEqual(
            recovery.PRESERVED_RECOVERY_TUPLE,
            (
                "ed34bfbe-b081-4e60-b787-393e6f600cce",
                "0d83b12fc8b16ca716f679fbb246ed11358c1a86",
                "10e7a938046e2d2d28ffa08a470bf9dfeda40dac",
            ),
        )


if __name__ == "__main__":
    unittest.main()

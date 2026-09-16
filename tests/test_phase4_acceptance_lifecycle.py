from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase4_acceptance_lifecycle as lifecycle  # noqa: E402


def owner(comment_id: int, body: str) -> dict:
    return {
        "id": comment_id,
        "body": body,
        "user": {"login": lifecycle.OWNER_LOGIN, "id": lifecycle.OWNER_ID},
    }


def bot(comment_id: int, body: str) -> dict:
    return {
        "id": comment_id,
        "body": body,
        "user": {"login": lifecycle.GITHUB_ACTIONS_LOGIN, "id": 41898282, "type": "Bot"},
    }


class AcceptanceLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.build_id = "12345678-abcd"
        self.image = lifecycle.IMAGE_PREFIX + "@sha256:" + "d" * 64
        self.findings = "e" * 64
        self.risk = "RISK-123"
        self.decision = 1234567890
        self.token_id = 1234567891
        self.run_id = 1234567892
        self.acceptance_body = (
            f"{lifecycle.ACCEPTANCE_PREFIX} "
            f"build={self.build_id} image={self.image} "
            f"findings_sha256={self.findings} risk={self.risk} "
            f"decision={self.decision}"
        )
        self.acceptance = owner(self.token_id, self.acceptance_body)

    def state(self, comments: list[dict]) -> dict:
        return lifecycle.lifecycle_state(
            [comments],
            build_id=self.build_id,
            image=self.image,
            findings_sha256=self.findings,
        )

    def consumption(self, token_id: int | None = None, **overrides: object) -> dict:
        acceptance_state = self.state([self.acceptance])
        body = lifecycle.consumption_body(acceptance_state, str(self.run_id))
        if token_id is not None:
            body = body.replace(
                f"token={self.token_id}", f"token={token_id}", 1
            )
        for key, value in overrides.items():
            old_value = {
                "build": self.build_id,
                "image": self.image,
                "findings_sha256": self.findings,
                "risk": self.risk,
                "decision": str(self.decision),
                "run": str(self.run_id),
            }[key]
            body = body.replace(f"{key}={old_value}", f"{key}={value}", 1)
        return bot(2234567891, body)

    def test_valid_unconsumed_token_is_accepted_for_one_use(self) -> None:
        state = self.state([self.acceptance])
        self.assertEqual(state["status"], "ACCEPTED_FOR_ONE_USE")
        self.assertTrue(state["historically_valid"])
        self.assertEqual(state["token_id"], self.token_id)

    def test_consumed_token_is_rejected_as_already_consumed(self) -> None:
        consumed = self.consumption()
        state = self.state([self.acceptance, consumed])
        self.assertEqual(state["status"], "REJECTED_AS_ALREADY_CONSUMED")
        self.assertEqual(state["consumption_run_id"], self.run_id)
        self.assertTrue(state["historically_valid"])

    def test_historical_risk002_token_is_preserved_but_non_reusable(self) -> None:
        legacy = owner(
            lifecycle.LEGACY_RISK002_TOKEN_ID,
            lifecycle.LEGACY_RISK002_BODY,
        )
        consumption = owner(
            2234567892,
            (
                f"{lifecycle.CONSUMPTION_PREFIX} "
                f"token={lifecycle.LEGACY_RISK002_TOKEN_ID} "
                f"build={lifecycle.LEGACY_RISK002_BUILD_ID} "
                f"image={lifecycle.LEGACY_RISK002_IMAGE} "
                f"findings_sha256={lifecycle.LEGACY_RISK002_FINDINGS_SHA256} "
                f"risk={lifecycle.LEGACY_RISK002_RISK} "
                f"decision={lifecycle.LEGACY_RISK002_DECISION} "
                "run=34742223023"
            ),
        )
        state = lifecycle.lifecycle_state(
            [legacy, consumption],
            build_id=lifecycle.LEGACY_RISK002_BUILD_ID,
            image=lifecycle.LEGACY_RISK002_IMAGE,
            findings_sha256=lifecycle.LEGACY_RISK002_FINDINGS_SHA256,
        )
        self.assertEqual(state["status"], "REJECTED_AS_ALREADY_CONSUMED")
        self.assertTrue(state["historically_valid"])
        self.assertEqual(state["version"], 1)

    def test_legacy_token_without_consumption_never_becomes_executable(self) -> None:
        legacy = owner(
            lifecycle.LEGACY_RISK002_TOKEN_ID,
            lifecycle.LEGACY_RISK002_BODY,
        )
        state = lifecycle.lifecycle_state(
            [legacy],
            build_id=lifecycle.LEGACY_RISK002_BUILD_ID,
            image=lifecycle.LEGACY_RISK002_IMAGE,
            findings_sha256=lifecycle.LEGACY_RISK002_FINDINGS_SHA256,
        )
        self.assertEqual(state["status"], "REJECTED_AS_LEGACY_CONSUMPTION_REQUIRED")

    def test_wrong_token_binding_does_not_consume_current_token(self) -> None:
        other = self.consumption(token_id=self.token_id + 100)
        state = self.state([self.acceptance, other])
        self.assertEqual(state["status"], "ACCEPTED_FOR_ONE_USE")

    def test_wrong_tuple_does_not_authorise_current_tuple(self) -> None:
        wrong = copy.deepcopy(self.acceptance)
        wrong["body"] = wrong["body"].replace(
            f"findings_sha256={self.findings}",
            "findings_sha256=" + "f" * 64,
        )
        with self.assertRaisesRegex(
            lifecycle.AcceptanceLifecycleError,
            "HIGH_ACCEPTANCE_OWNER_DISPOSITION_INVALID",
        ):
            self.state([wrong])

    def test_duplicate_consumption_fails_closed(self) -> None:
        first = self.consumption()
        second = copy.deepcopy(first)
        second["id"] += 1
        with self.assertRaisesRegex(
            lifecycle.AcceptanceLifecycleError,
            "HIGH_ACCEPTANCE_CONSUMPTION_AMBIGUOUS",
        ):
            self.state([self.acceptance, first, second])

    def test_conflicting_consumption_binding_fails_closed(self) -> None:
        bad = self.consumption(risk="RISK-999")
        with self.assertRaisesRegex(
            lifecycle.AcceptanceLifecycleError,
            "HIGH_ACCEPTANCE_CONSUMPTION_BINDING_CONFLICT",
        ):
            self.state([self.acceptance, bad])

    def test_malformed_consumption_fails_closed(self) -> None:
        malformed = bot(
            2234567891,
            f"{lifecycle.CONSUMPTION_PREFIX} token={self.token_id}",
        )
        with self.assertRaisesRegex(
            lifecycle.AcceptanceLifecycleError,
            "PHASE4_HIGH_ACCEPTANCE_CONSUMED_V1_FORMAT_INVALID",
        ):
            self.state([self.acceptance, malformed])

    def test_duplicate_matching_acceptance_fails_closed(self) -> None:
        duplicate = copy.deepcopy(self.acceptance)
        duplicate["id"] += 1
        with self.assertRaisesRegex(
            lifecycle.AcceptanceLifecycleError,
            "HIGH_ACCEPTANCE_OWNER_DISPOSITION_INVALID",
        ):
            self.state([self.acceptance, duplicate])

    def test_non_authoritative_consumption_cannot_consume_token(self) -> None:
        bad = self.consumption()
        bad["user"] = {"login": "someone-else", "id": 1}
        state = self.state([self.acceptance, bad])
        self.assertEqual(state["status"], "ACCEPTED_FOR_ONE_USE")

    def test_verify_consumed_binds_run_identity(self) -> None:
        acceptance_state = self.state([self.acceptance])
        consumed = self.consumption()
        state = lifecycle.verify_consumed(
            [self.acceptance, consumed],
            acceptance=acceptance_state,
            run_id=str(self.run_id),
        )
        self.assertEqual(state["status"], "REJECTED_AS_ALREADY_CONSUMED")
        with self.assertRaisesRegex(
            lifecycle.AcceptanceLifecycleError,
            "HIGH_ACCEPTANCE_CONSUMPTION_NOT_CONFIRMED",
        ):
            lifecycle.verify_consumed(
                [self.acceptance, consumed],
                acceptance=acceptance_state,
                run_id=str(self.run_id + 1),
            )

    def test_finding_digest_is_order_independent_and_high_critical_only(self) -> None:
        first = {
            "occurrences": [
                {
                    "name": "occ/high",
                    "noteName": "notes/CVE-1",
                    "vulnerability": {
                        "effectiveSeverity": "HIGH",
                        "packageIssue": [
                            {
                                "affectedPackage": "zlib",
                                "affectedVersion": {"name": "1"},
                                "fixedVersion": {"kind": "MAXIMUM"},
                            }
                        ],
                    },
                },
                {
                    "name": "occ/low",
                    "noteName": "notes/CVE-low",
                    "vulnerability": {"effectiveSeverity": "LOW"},
                },
                {
                    "name": "occ/critical",
                    "noteName": "notes/CVE-2",
                    "vulnerability": {
                        "effectiveSeverity": "CRITICAL",
                        "packageIssue": [],
                    },
                },
            ]
        }
        second = {"occurrences": list(reversed(first["occurrences"]))}
        self.assertEqual(
            lifecycle.findings_sha256(first),
            lifecycle.findings_sha256(second),
        )

    def test_empty_high_critical_set_cannot_create_acceptance_fingerprint(self) -> None:
        with self.assertRaisesRegex(
            lifecycle.AcceptanceLifecycleError,
            "HIGH_ACCEPTANCE_FINDINGS_EMPTY",
        ):
            lifecycle.findings_sha256(
                {
                    "occurrences": [
                        {
                            "name": "occ/low",
                            "noteName": "notes/CVE-low",
                            "vulnerability": {"effectiveSeverity": "LOW"},
                        }
                    ]
                }
            )


class AcceptanceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = (
            ROOT / ".github/workflows/phase4-evidence-reusable.yml"
        ).read_text(encoding="utf-8")
        cls.caller = (
            ROOT / ".github/workflows/phase4-evidence.yml"
        ).read_text(encoding="utf-8")

    def test_consumption_is_serialised_and_issue_write_is_bounded_to_evidence_path(self) -> None:
        self.assertIn(
            "group: resilio-phase4-high-acceptance-consumer",
            self.workflow,
        )
        self.assertIn("cancel-in-progress: false", self.workflow)
        self.assertIn("      issues: write", self.workflow)
        self.assertIn("      issues: write", self.caller)

    def test_new_lifecycle_replaces_legacy_live_checker(self) -> None:
        self.assertNotIn(
            "phase4_supply_chain.py check-high-acceptance",
            self.workflow,
        )
        for required in (
            "phase4_acceptance_lifecycle.py findings-sha256",
            "phase4_acceptance_lifecycle.py check-available",
            "phase4_acceptance_lifecycle.py consumption-body",
            "phase4_acceptance_lifecycle.py verify-consumed",
        ):
            self.assertIn(required, self.workflow)

    def test_consumption_is_written_once_and_reconciled_before_pass(self) -> None:
        check = self.workflow.index(
            "phase4_acceptance_lifecycle.py check-available"
        )
        create = self.workflow.index(
            'gh api --method POST "repos/$GITHUB_REPOSITORY/issues/28/comments"'
        )
        verify = self.workflow.index(
            "phase4_acceptance_lifecycle.py verify-consumed"
        )
        passed = self.workflow.index("          DISP=PASS", verify)
        provenance = self.workflow.index(
            "phase4_supply_chain.py provenance-occurrence"
        )
        self.assertLess(check, create)
        self.assertLess(create, verify)
        self.assertLess(verify, passed)
        self.assertLess(passed, provenance)
        self.assertEqual(
            self.workflow.count(
                'gh api --method POST "repos/$GITHUB_REPOSITORY/issues/28/comments"'
            ),
            1,
        )

    def test_ambiguous_create_outcome_reconciles_without_retry(self) -> None:
        self.assertIn("CONSUMPTION_CREATE_RC=$?", self.workflow)
        self.assertIn("CONSUMPTION_CREATE_OUTCOME_AMBIGUOUS_RECONCILE", self.workflow)
        self.assertIn("high-comments-after.json", self.workflow)
        self.assertNotIn("for _ in $(seq", self.workflow[
            self.workflow.index("CONSUMPTION_CREATE_RC=$?"):
            self.workflow.index("phase4_acceptance_lifecycle.py verify-consumed")
        ])


if __name__ == "__main__":
    unittest.main()

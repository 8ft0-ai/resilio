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
        cls.adjudicate = cls.workflow[
            cls.workflow.index("  adjudicate:\n"):
            cls.workflow.index("  consume_acceptance:\n")
        ]
        cls.consume = cls.workflow[
            cls.workflow.index("  consume_acceptance:\n"):
            cls.workflow.index("  evidence:\n")
        ]
        cls.evidence = cls.workflow[cls.workflow.index("  evidence:\n"):]

    def test_consumption_is_serialised_and_issue_write_is_job_isolated(self) -> None:
        concurrency = self.workflow.index(
            "concurrency:\n  group: resilio-phase4-high-acceptance-consumer"
        )
        self.assertLess(concurrency, self.workflow.index("jobs:\n"))
        self.assertIn("cancel-in-progress: false", self.workflow[: self.workflow.index("jobs:\n")])
        self.assertEqual(self.workflow.count("      issues: write"), 1)
        self.assertNotIn("issues: write", self.adjudicate)
        self.assertIn("      issues: write", self.consume)
        self.assertNotIn("issues: write", self.evidence)
        self.assertIn("      issues: write", self.caller)
        self.assertNotIn("contents: read", self.consume)
        self.assertNotIn("id-token: write", self.consume)

    def test_issue_write_job_runs_only_for_high_review_required(self) -> None:
        self.assertIn(
            "if: needs.adjudicate.outputs.gate == 'HIGH_REVIEW_REQUIRED'",
            self.consume,
        )
        self.assertIn("needs: [adjudicate, consume_acceptance]", self.evidence)
        self.assertIn("always() &&", self.evidence)
        self.assertIn("!cancelled() &&", self.evidence)
        self.assertIn(
            "needs.adjudicate.outputs.gate == 'PASS' && needs.consume_acceptance.result == 'skipped'",
            self.evidence,
        )
        self.assertIn(
            "needs.adjudicate.outputs.gate == 'HIGH_REVIEW_REQUIRED' && needs.consume_acceptance.result == 'success'",
            self.evidence,
        )

    def test_new_lifecycle_replaces_legacy_live_checker(self) -> None:
        self.assertNotIn(
            "phase4_supply_chain.py check-high-acceptance",
            self.workflow,
        )
        self.assertIn(
            "phase4_acceptance_lifecycle.py findings-sha256",
            self.workflow,
        )
        for required in (
            '"$LIFECYCLE_HELPER" check-available',
            '"$LIFECYCLE_HELPER" consumption-body',
            '"$LIFECYCLE_HELPER" verify-consumed',
        ):
            self.assertIn(required, self.consume)

    def test_issue_write_job_has_no_downloaded_action_or_ambient_token(self) -> None:
        self.assertNotIn("uses:", self.consume)
        self.assertEqual(
            self.consume.count("          GH_TOKEN: ${{ github.token }}"),
            3,
        )
        self.assertEqual(self.consume.count("${{ github.token }}"), 3)
        self.assertNotIn('GH_TOKEN="${{ github.token }}" gh api', self.consume)
        self.assertEqual(self.consume.count("gh api"), 3)

        def step(name: str) -> str:
            marker = f"      - name: {name}\n"
            begin = self.consume.index(marker)
            finish = self.consume.find("\n      - name: ", begin + len(marker))
            if finish == -1:
                finish = len(self.consume)
            return self.consume[begin:finish]

        token_steps = (
            "Read HIGH acceptance comments",
            "Attempt HIGH acceptance consumption once",
            "Read HIGH acceptance comments after consumption",
        )
        for name in token_steps:
            block = step(name)
            self.assertIn("          GH_TOKEN: ${{ github.token }}", block)
            run = block[block.index("        run: |") :]
            self.assertNotIn("${{ github.token }}", run)
            self.assertEqual(run.count("gh api"), 1)
            self.assertNotIn("python3", run)
            self.assertNotIn("LIFECYCLE_HELPER", run)

        helper_steps = (
            "Fetch exact lifecycle helper without GitHub credentials",
            "Prepare HIGH acceptance consumption",
            "Verify HIGH acceptance consumption",
        )
        for name in helper_steps:
            block = step(name)
            self.assertNotIn("${{ github.token }}", block)
            self.assertNotIn("\n          GH_TOKEN:", block)

        self.assertIn(
            "https://raw.githubusercontent.com/$WORKFLOW_REPOSITORY/$WORKFLOW_SHA/"
            "scripts/phase4_acceptance_lifecycle.py",
            self.consume,
        )
        self.assertIn(
            'test "$(git hash-object "$LIFECYCLE_HELPER")" = '
            '"b302048ecc870925a73d790b3b602f48e6116143"',
            self.consume,
        )
        self.assertIn('test -z "${GH_TOKEN:-}"', self.consume)
        self.assertIn('test -z "${GITHUB_TOKEN:-}"', self.consume)

    def test_consumption_is_written_once_and_reconciled_before_evidence(self) -> None:
        check = self.consume.index('"$LIFECYCLE_HELPER" check-available')
        create = self.consume.index("gh api --method POST")
        verify = self.consume.index('"$LIFECYCLE_HELPER" verify-consumed')
        self.assertLess(check, create)
        self.assertLess(create, verify)
        self.assertEqual(self.workflow.count("gh api --method POST"), 1)
        self.assertNotIn('"$LIFECYCLE_HELPER" verify-consumed', self.evidence)
        self.assertIn('"$SYFT_BIN" version > "$SYFT_VERSION"', self.evidence)

    def test_ambiguous_create_outcome_reconciles_without_retry(self) -> None:
        self.assertIn("CONSUMPTION_CREATE_RC=$?", self.consume)
        self.assertIn("CONSUMPTION_CREATE_OUTCOME_AMBIGUOUS_RECONCILE", self.consume)
        self.assertIn("high-comments-after.json", self.consume)
        create_to_verify = self.consume[
            self.consume.index("CONSUMPTION_CREATE_RC=$?"):
            self.consume.index('"$LIFECYCLE_HELPER" verify-consumed')
        ]
        self.assertNotIn("for _ in $(seq", create_to_verify)

    def test_syft_job_has_no_issue_write_token_or_checkout_credential(self) -> None:
        self.assertNotIn("issues: write", self.evidence)
        result_step = self.evidence[self.evidence.index("      - name: Generate provenance and repository SBOM evidence"):]
        self.assertNotIn("GH_TOKEN", result_step)
        self.assertNotIn("GITHUB_TOKEN", result_step)
        self.assertNotIn("${{ github.token }}", result_step)
        self.assertIn('test -z "${GH_TOKEN:-}"', self.evidence)
        self.assertIn('test -z "${GITHUB_TOKEN:-}"', self.evidence)
        self.assertIn('test ! -f "$HOME/.git-credentials"', self.evidence)
        self.assertIn("GITHUB_CHECKOUT_CREDENTIAL_REMAINS", self.evidence)
        self.assertIn("persist-credentials: false", self.evidence)
        self.assertIn('"$SYFT_BIN" "$IMAGE" \\', self.evidence)

    def test_adjudication_passes_only_immutable_non_secret_gate_data(self) -> None:
        for output in (
            "gate",
            "findings_sha256",
            "image",
            "source_sha",
            "workflow_sha",
            "source_tree_sha",
        ):
            self.assertIn(f"      {output}: ${{{{ steps.result.outputs.{output} }}}}", self.adjudicate)
        self.assertNotIn("acceptance_token", self.adjudicate)
        self.assertNotIn("consumption_comment", self.adjudicate)
        self.assertNotIn("github.token", self.evidence[self.evidence.index("      - name: Generate provenance and repository SBOM evidence"):])

    def test_activation_remains_pinned_to_current_production_reusable(self) -> None:
        self.assertIn(
            "uses: 8ft0-ai/resilio/.github/workflows/phase4-evidence-reusable.yml@"
            "9ef1edfad9538418e3f4936c8580c4401b49e514",
            self.caller,
        )


if __name__ == "__main__":
    unittest.main()

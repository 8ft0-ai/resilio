"""Hostile tests for the bounded C4->C5 bootstrap transition relation."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_cloud_bootstrap", ROOT / "scripts/validate_cloud_bootstrap.py"
)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(validator)

PHASE5 = ROOT / "infra/bootstrap/phase5_authority.tf"


class C5BootstrapTransitionTests(unittest.TestCase):
    def setUp(self):
        self.successor = PHASE5.read_bytes()
        self.old = (
            validator.C5_RECOVERY_WORKFLOW_PREFIX
            + validator.C5_PREDECESSOR_RECOVERY_SHA
        ).encode("ascii")
        self.new = (
            validator.C5_RECOVERY_WORKFLOW_PREFIX + validator.C5_CONTROL_SHA
        ).encode("ascii")
        self.predecessor = self.successor.replace(self.new, self.old, 1)

    def test_canonical_predecessor_is_recognised(self):
        self.assertTrue(
            validator.is_canonical_c5_phase5_authority_transition(self.predecessor)
        )

    def test_exact_c4_to_c5_transition_is_accepted(self):
        self.assertTrue(
            validator.is_canonical_c5_phase5_authority_transition(self.successor)
        )

    def test_additional_phase5_authority_change_is_rejected(self):
        self.assertFalse(
            validator.is_canonical_c5_phase5_authority_transition(
                self.successor + b"\n# unauthorised\n"
            )
        )

    def test_wrong_old_pin_is_rejected(self):
        wrong = self.predecessor.replace(
            validator.C5_PREDECESSOR_RECOVERY_SHA.encode("ascii"),
            b"1111111111111111111111111111111111111111",
            1,
        )
        self.assertFalse(validator.is_canonical_c5_phase5_authority_transition(wrong))

    def test_wrong_c5_target_is_rejected(self):
        wrong = self.successor.replace(
            validator.C5_CONTROL_SHA.encode("ascii"),
            b"2222222222222222222222222222222222222222",
            1,
        )
        self.assertFalse(validator.is_canonical_c5_phase5_authority_transition(wrong))


if __name__ == "__main__":
    unittest.main()

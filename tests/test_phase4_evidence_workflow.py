from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/phase4-evidence-reusable.yml"


class Phase4EvidenceWorkflowTests(unittest.TestCase):
    def test_export_sbom_transient_path_reconciles_without_replaying_post(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")

        # ExportSBOM is not documented as idempotent, so the workflow may issue
        # the POST at most once per evidence attempt and must reconcile state
        # after an ambiguous transient response rather than blindly replay it.
        self.assertEqual(text.count("artifact_analysis_request EXPORT_SBOM"), 1)
        precheck = text.index("sbom-reference-precheck")
        export = text.index("artifact_analysis_request EXPORT_SBOM")
        self.assertLess(precheck, export)
        self.assertIn("SBOM_REFERENCE_REUSED", text)

        self.assertIn('c == 429 or 500 <= c <= 599', text)
        self.assertIn("EXPORT_SBOM_TRANSIENT_RECONCILE", text)
        self.assertIn('if test "$EXPORT_TRANSIENT" != "yes"; then', text)
        self.assertIn('cat "$EXPORT_DIAGNOSTIC"', text)
        self.assertIn('exit "$EXPORT_RC"', text)

        reconcile_loop = text.index("for _ in $(seq 1 30); do", export)
        self.assertGreater(reconcile_loop, export)
        self.assertIn("sleep 10", text[reconcile_loop:])
        self.assertIn('test "$SBOM_REF_COUNT" -le 1', text[precheck:])


if __name__ == "__main__":
    unittest.main()

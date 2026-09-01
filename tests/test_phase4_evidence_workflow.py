from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/phase4-evidence-reusable.yml"


def workflow_sections() -> tuple[str, str, str]:
    text = WORKFLOW.read_text(encoding="utf-8")
    function_start = text.index("          artifact_analysis_request() {")
    function_end = text.index("\n\n          collect_occurrences() {", function_start)
    export_start = text.index("          SBOM_REF_RESPONSE=")
    export_end = text.index("\n\n          SBOM_BUCKET=", export_start)
    return (
        text,
        textwrap.dedent(text[function_start:function_end]),
        textwrap.dedent(text[export_start:export_end]),
    )


class Phase4EvidenceWorkflowTests(unittest.TestCase):
    def test_export_sbom_transient_path_reconciles_without_replaying_post(self) -> None:
        text, request_function, _ = workflow_sections()

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

        # The request helper must not mutate the caller's errexit state. Curl is
        # captured in an if-condition so normal callers still fail on a non-zero
        # diagnostic while the ExportSBOM caller can deliberately inspect it.
        self.assertNotIn("set +e", request_function)
        self.assertNotIn("set -e", request_function)
        self.assertIn('if HTTP_STATUS="$(curl', request_function)

    def _run_transient_harness(self, scenario: str) -> tuple[subprocess.CompletedProcess[str], int]:
        _, request_function, export_block = workflow_sections()
        valid_occurrence = (
            '{"name":"projects/resilio-control-e882d4/occurrences/sbom-1",'
            '"sbomReference":{"payload":{"predicate":{'
            '"location":"gs://sbom-bucket/sbom.json",'
            '"digest":{"sha256":"' + ("0" * 64) + '"}}}}}'
        )
        harness = (
            "set -euo pipefail\n"
            'SCENARIO="$1"\n'
            'RUNNER_TEMP="$2"\n'
            'mkdir -p "$RUNNER_TEMP"\n'
            'TOKEN="test-token"\n'
            'BUILD_ID="ed34bfbe-b081-4e60-b787-393e6f600cce"\n'
            'GITHUB_RUN_ID="123456"\n'
            'RESOURCE_URL="https://us-central1-docker.pkg.dev/resilio-control-e882d4/resilio-phase4/phase4-proof@sha256:'
            + ("1" * 64)
            + '"\n'
            'ENCODED="test-resource"\n'
            'POST_COUNT="$RUNNER_TEMP/post-count"\n\n'
            + request_function
            + "\n\n"
            + "curl() {\n"
            + '  local output=""\n'
            + '  while test "$#" -gt 0; do\n'
            + '    if test "$1" = "--output"; then\n'
            + '      output="$2"\n'
            + '      shift 2\n'
            + "      continue\n"
            + "    fi\n"
            + "    shift\n"
            + "  done\n"
            + '  test -n "$output"\n'
            + "  printf '%s\\n' '{\"error\":{\"code\":503,\"status\":\"UNAVAILABLE\"}}' > \"$output\"\n"
            + '  local count=0\n'
            + '  if test -f "$POST_COUNT"; then count="$(cat "$POST_COUNT")"; fi\n'
            + "  printf '%s\\n' \"$((count + 1))\" > \"$POST_COUNT\"\n"
            + "  printf '503'\n"
            + "}\n\n"
            + "sleep() { :; }\n\n"
            + "collect_occurrences() {\n"
            + '  local _filter="$1" prefix="$2" _category="$3" out="$4"\n'
            + '  if test "$prefix" = "sbom-reference-precheck"; then\n'
            + "    printf '%s\\n' '{\"occurrences\":[]}' > \"$out\"\n"
            + "    return 0\n"
            + "  fi\n"
            + "  case \"$SCENARIO\" in\n"
            + "    success)\n"
            + "      printf '%s\\n' '{\"occurrences\":["
            + valid_occurrence.replace("'", "'\\''")
            + "]}' > \"$out\"\n"
            + "      ;;\n"
            + "    missing)\n"
            + "      printf '%s\\n' '{\"occurrences\":[]}' > \"$out\"\n"
            + "      ;;\n"
            + "    ambiguous)\n"
            + "      printf '%s\\n' '{\"occurrences\":["
            + valid_occurrence.replace("'", "'\\''")
            + ","
            + valid_occurrence.replace("'", "'\\''")
            + "]}' > \"$out\"\n"
            + "      ;;\n"
            + "    *) exit 97 ;;\n"
            + "  esac\n"
            + "}\n\n"
            + export_block
            + "\n"
            + "printf 'BLOCK_COMPLETE\\n'\n"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            run_dir = temp / "runner"
            script = temp / "harness.sh"
            script.write_text(harness, encoding="utf-8")
            result = subprocess.run(
                ["bash", str(script), scenario, str(run_dir)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            count_file = run_dir / "post-count"
            post_count = int(count_file.read_text(encoding="utf-8").strip()) if count_file.exists() else 0
            return result, post_count

    def test_simulated_503_reaches_reconciliation_without_replay(self) -> None:
        result, post_count = self._run_transient_harness("success")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("EXPORT_SBOM_TRANSIENT_RECONCILE", result.stdout)
        self.assertIn("BLOCK_COMPLETE", result.stdout)
        self.assertEqual(post_count, 1)

    def test_simulated_503_missing_reconciled_evidence_fails(self) -> None:
        result, post_count = self._run_transient_harness("missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("BLOCK_COMPLETE", result.stdout)
        self.assertEqual(post_count, 1)

    def test_simulated_503_ambiguous_reconciled_evidence_fails(self) -> None:
        result, post_count = self._run_transient_harness("ambiguous")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("BLOCK_COMPLETE", result.stdout)
        self.assertEqual(post_count, 1)


if __name__ == "__main__":
    unittest.main()

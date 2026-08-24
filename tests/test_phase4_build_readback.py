from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase4_supply_chain as p4  # noqa: E402


class BuildReadbackDefaultsTests(unittest.TestCase):
    def _build(self) -> dict:
        source, workflow = "a" * 40, "b" * 40
        build = copy.deepcopy(p4.build_request(source, workflow))
        build.update(
            {
                "id": "12345678-abcd",
                "status": "SUCCESS",
                "sourceProvenance": {
                    "resolvedGitSource": {
                        "url": p4.SOURCE_URL,
                        "revision": source,
                    }
                },
                "results": {
                    "images": [
                        {
                            "name": p4.image_tag(source),
                            "digest": "sha256:" + "c" * 64,
                        }
                    ]
                },
            }
        )
        return build

    def test_provider_omission_of_must_match_default_is_accepted(self) -> None:
        build = self._build()
        del build["options"]["substitutionOption"]
        build["options"]["pool"] = {}

        result = p4.validate_build(build, "a" * 40, "b" * 40)

        self.assertEqual(result["build_id"], "12345678-abcd")
        self.assertEqual(
            p4.build_request("a" * 40, "b" * 40)["options"]["substitutionOption"],
            "MUST_MATCH",
        )

    def test_explicit_allow_loose_remains_rejected(self) -> None:
        build = self._build()
        build["options"]["substitutionOption"] = "ALLOW_LOOSE"

        with self.assertRaisesRegex(p4.SupplyChainError, "BUILD_OPTIONS_MISMATCH"):
            p4.validate_build(build, "a" * 40, "b" * 40)


if __name__ == "__main__":
    unittest.main()

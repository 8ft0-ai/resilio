from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase4_evidence_readback as readback  # noqa: E402
import phase4_supply_chain as p4  # noqa: E402


class EvidenceBuildReadbackTests(unittest.TestCase):
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

    def test_exact_provider_artifacts_images_mirror_is_accepted(self) -> None:
        build = self._build()
        build["artifacts"] = {"images": list(build["images"])}

        result = readback.validate_build_readback(build, "a" * 40, "b" * 40)

        self.assertEqual(result["build_id"], "12345678-abcd")
        self.assertNotIn("artifacts", readback.normalize_build_readback(build))

    def test_different_artifacts_image_is_rejected(self) -> None:
        build = self._build()
        build["artifacts"] = {"images": [p4.IMAGE_PREFIX + ":different"]}

        with self.assertRaisesRegex(p4.SupplyChainError, "BUILD_ARTIFACTS_MIRROR_MISMATCH"):
            readback.validate_build_readback(build, "a" * 40, "b" * 40)

    def test_extra_artifact_class_is_rejected(self) -> None:
        build = self._build()
        build["artifacts"] = {
            "images": list(build["images"]),
            "objects": {"location": "gs://unexpected", "paths": ["*"]},
        }

        with self.assertRaisesRegex(p4.SupplyChainError, "BUILD_ARTIFACTS_MIRROR_MISMATCH"):
            readback.validate_build_readback(build, "a" * 40, "b" * 40)


if __name__ == "__main__":
    unittest.main()

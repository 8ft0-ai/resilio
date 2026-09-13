from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase4_repository_sbom as sbom  # noqa: E402


class RepositorySbomTests(unittest.TestCase):
    def setUp(self) -> None:
        self.build_id = "16251096-2ad8-40b7-a8d4-6a4bbacb0928"
        self.image = sbom.IMAGE_PREFIX + "@sha256:" + "4" * 64
        self.content = json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "SPDXID": "SPDXRef-DOCUMENT",
                "name": "synthetic-fixture",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self.metadata = {
            "bucket": sbom.EVIDENCE_BUCKET,
            "name": sbom.sbom_object(self.build_id),
            "generation": "12345",
        }

    def test_generator_identity_is_immutable_and_reconstructable(self) -> None:
        identity = sbom.generator_identity()
        self.assertEqual(identity["name"], "syft")
        self.assertEqual(identity["version"], "1.51.1")
        self.assertEqual(identity["asset"], "syft_1.51.1_linux_amd64.tar.gz")
        self.assertRegex(identity["archive_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(identity["output_format"], "spdx-json")
        self.assertNotIn("latest", json.dumps(identity))

    def test_exact_digest_only_and_mutable_reference_rejected(self) -> None:
        self.assertEqual(sbom.require_exact_image(self.image), self.image)
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_IMAGE_DIGEST_INVALID"):
            sbom.require_exact_image(sbom.IMAGE_PREFIX + ":latest")
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_IMAGE_DIGEST_INVALID"):
            sbom.require_exact_image(sbom.IMAGE_PREFIX + ":candidate")

    def test_generator_archive_and_version_mismatch_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "syft.tgz"
            archive.write_bytes(b"wrong")
            version = Path(directory) / "version.txt"
            version.write_text("Application: syft\nVersion: 1.51.1\n", encoding="utf-8")
            with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_GENERATOR_CHECKSUM_MISMATCH"):
                sbom.verify_generator_archive(str(archive))
            original = sbom.GENERATOR_ARCHIVE_SHA256
            try:
                sbom.GENERATOR_ARCHIVE_SHA256 = sbom.sha256_bytes(b"wrong")
                sbom.verify_generator_archive(str(archive))
                version.write_text("Application: syft\nVersion: 1.52.0\n", encoding="utf-8")
                with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_GENERATOR_VERSION_MISMATCH"):
                    sbom.verify_generator_version(str(version))
            finally:
                sbom.GENERATOR_ARCHIVE_SHA256 = original

    def test_binding_covers_exact_image_generator_content_and_storage_generation(self) -> None:
        record = sbom.bind_repository_sbom(
            self.image, self.build_id, self.metadata, self.content,
        )
        self.assertEqual(record["occurrence"], "repository-generator/syft/1.51.1")
        self.assertEqual(record["image"], self.image)
        self.assertEqual(record["generator"], sbom.generator_identity())
        self.assertEqual(record["sha256"], sbom.sha256_bytes(self.content))
        self.assertEqual(record["location"], "gs://" + sbom.EVIDENCE_BUCKET + "/" + sbom.sbom_object(self.build_id))
        self.assertEqual(record["generation"], "12345")
        self.assertRegex(record["binding_sha256"], r"^[0-9a-f]{64}$")
        sbom.validate_sbom_record(record, self.image, self.build_id, self.content)

        changed = copy.deepcopy(record)
        changed["image"] = sbom.IMAGE_PREFIX + "@sha256:" + "5" * 64
        with self.assertRaises(sbom.RepositorySbomError):
            sbom.validate_sbom_record(changed, self.image, self.build_id, self.content)

        changed = copy.deepcopy(record)
        changed["generator"]["version"] = "1.52.0"
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_GENERATOR_IDENTITY_MISMATCH"):
            sbom.validate_sbom_record(changed, self.image, self.build_id, self.content)

        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_CONTENT_DIGEST_MISMATCH"):
            sbom.validate_sbom_record(record, self.image, self.build_id, self.content + b"\n")

    def test_storage_namespace_generation_and_duplicate_target_are_fixed(self) -> None:
        self.assertEqual(
            sbom.sbom_object(self.build_id),
            f"transitions/{self.build_id}.sbom.spdx.json",
        )
        bad_bucket = dict(self.metadata)
        bad_bucket["bucket"] = "other"
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_STORAGE_OBJECT_MISMATCH"):
            sbom.bind_repository_sbom(self.image, self.build_id, bad_bucket, self.content)
        bad_name = dict(self.metadata)
        bad_name["name"] = "elsewhere/object.json"
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_STORAGE_OBJECT_MISMATCH"):
            sbom.bind_repository_sbom(self.image, self.build_id, bad_name, self.content)
        bad_generation = dict(self.metadata)
        bad_generation["generation"] = "0"
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_STORAGE_GENERATION_INVALID"):
            sbom.bind_repository_sbom(self.image, self.build_id, bad_generation, self.content)

    def test_transition_must_match_bound_sbom_record(self) -> None:
        record = sbom.bind_repository_sbom(
            self.image, self.build_id, self.metadata, self.content,
        )
        manifest = {
            "build_id": self.build_id,
            "image": self.image,
            "sbom": record,
        }
        sbom.validate_transition(manifest, self.image, self.build_id, self.content)
        bad = copy.deepcopy(manifest)
        bad["sbom"]["binding_sha256"] = "0" * 64
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_BINDING_DIGEST_MISMATCH"):
            sbom.validate_transition(bad, self.image, self.build_id, self.content)

    def test_spdx_shape_is_required(self) -> None:
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_CONTENT_SPDX"):
            sbom.bind_repository_sbom(
                self.image,
                self.build_id,
                self.metadata,
                b'{"SPDXID":"SPDXRef-DOCUMENT"}',
            )


if __name__ == "__main__":
    unittest.main()

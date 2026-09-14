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
        self.digest = "sha256:" + "4" * 64
        self.image = sbom.IMAGE_PREFIX + "@" + self.digest
        self.content = json.dumps(
            {"spdxVersion": "SPDX-2.3", "SPDXID": "SPDXRef-DOCUMENT", "name": "synthetic-fixture"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self.syft = {
            "source": {
                "type": "image",
                "metadata": {
                    "userInput": self.image,
                    "manifestDigest": self.digest,
                    "repoDigests": [self.image],
                }
            }
        }
        self.upload = {
            "bucket": sbom.EVIDENCE_BUCKET,
            "name": sbom.sbom_object(self.build_id),
            "generation": "12345",
            "size": str(len(self.content)),
        }
        self.readback = dict(self.upload)

    def bind(self, *, content: bytes | None = None, readback: bytes | None = None,
             upload: dict | None = None, readback_metadata: dict | None = None,
             syft: dict | None = None) -> dict:
        content = self.content if content is None else content
        readback = content if readback is None else readback
        return sbom.bind_repository_sbom(
            self.image,
            self.build_id,
            self.upload if upload is None else upload,
            self.readback if readback_metadata is None else readback_metadata,
            content,
            readback,
            self.syft if syft is None else syft,
        )

    def test_generator_identity_is_immutable_and_reconstructable(self) -> None:
        identity = sbom.generator_identity()
        self.assertEqual(identity["name"], "syft")
        self.assertEqual(identity["version"], "1.51.1")
        self.assertEqual(identity["asset"], "syft_1.51.1_linux_amd64.tar.gz")
        self.assertRegex(identity["archive_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(identity["output_format"], "spdx-json")
        self.assertNotIn("latest", json.dumps(identity))

    def test_exact_resolved_manifest_digest_passes(self) -> None:
        self.assertEqual(sbom.resolved_manifest_digest(self.image, self.syft), self.digest)

    def test_absent_or_input_only_resolved_digest_fails(self) -> None:
        metadata = {"source": {"type": "image", "metadata": {"userInput": self.image, "repoDigests": [self.image]}}}
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_GENERATOR_MANIFEST_DIGEST_INVALID"):
            sbom.resolved_manifest_digest(self.image, metadata)

    def test_different_or_incompatible_resolved_digest_fails(self) -> None:
        changed = copy.deepcopy(self.syft)
        changed["source"]["metadata"]["manifestDigest"] = "sha256:" + "5" * 64
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_GENERATOR_MANIFEST_DIGEST_AMBIGUOUS"):
            sbom.resolved_manifest_digest(self.image, changed)
        changed = copy.deepcopy(self.syft)
        changed["source"]["metadata"]["manifestDigest"] = "sha256:" + "5" * 64
        changed["source"]["metadata"]["repoDigests"] = []
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_GENERATOR_MANIFEST_DIGEST_MISMATCH"):
            sbom.resolved_manifest_digest(self.image, changed)

    def test_mutable_or_wrong_algorithm_identity_cannot_satisfy_resolved_check(self) -> None:
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_IMAGE_DIGEST_INVALID"):
            sbom.resolved_manifest_digest(sbom.IMAGE_PREFIX + ":latest", self.syft)
        changed = copy.deepcopy(self.syft)
        changed["source"]["metadata"]["manifestDigest"] = "sha512:" + "4" * 64
        changed["source"]["metadata"]["repoDigests"] = []
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_GENERATOR_MANIFEST_DIGEST_INVALID"):
            sbom.resolved_manifest_digest(self.image, changed)

    def test_malformed_generator_metadata_fails(self) -> None:
        for payload in ([], {}, {"source": []}, {"source": {"type": "directory", "metadata": {}}}, {"source": {"type": "image", "metadata": []}}):
            with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_GENERATOR_METADATA_INVALID"):
                sbom.resolved_manifest_digest(self.image, payload)  # type: ignore[arg-type]
        changed = copy.deepcopy(self.syft)
        changed["source"]["metadata"]["repoDigests"] = self.image
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_GENERATOR_METADATA_INVALID"):
            sbom.resolved_manifest_digest(self.image, changed)

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

    def test_generation_specific_readback_and_matching_bytes_pass(self) -> None:
        record = self.bind()
        self.assertEqual(record["resolved_manifest_digest"], self.digest)
        self.assertEqual(record["generation"], "12345")
        self.assertEqual(record["sha256"], sbom.sha256_bytes(self.content))
        self.assertEqual(record["size_bytes"], len(self.content))
        sbom.validate_sbom_record(
            record, self.image, self.build_id, self.content, self.content, self.syft,
        )

    def test_wrong_or_missing_readback_generation_fails(self) -> None:
        wrong = dict(self.readback)
        wrong["generation"] = "12346"
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_STORAGE_READBACK_IDENTITY_MISMATCH"):
            self.bind(readback_metadata=wrong)
        missing = dict(self.readback)
        missing.pop("generation")
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_STORAGE_GENERATION_INVALID"):
            self.bind(readback_metadata=missing)

    def test_bucket_or_name_readback_mismatch_fails(self) -> None:
        for key, value in (("bucket", "other"), ("name", "transitions/other.sbom.spdx.json")):
            changed = dict(self.readback)
            changed[key] = value
            with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_STORAGE_OBJECT_MISMATCH"):
                self.bind(readback_metadata=changed)

    def test_altered_or_truncated_readback_fails(self) -> None:
        altered = self.content + b"\n"
        altered_metadata = dict(self.readback)
        altered_metadata["size"] = str(len(altered))
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_STORAGE_READBACK_SIZE_MISMATCH|SBOM_STORAGE_READBACK_DIGEST_MISMATCH"):
            self.bind(readback=altered, readback_metadata=altered_metadata)
        truncated = self.content[:-1]
        truncated_metadata = dict(self.readback)
        truncated_metadata["size"] = str(len(truncated))
        with self.assertRaises(sbom.RepositorySbomError):
            self.bind(readback=truncated, readback_metadata=truncated_metadata)

    def test_readback_metadata_size_mismatch_fails(self) -> None:
        changed = dict(self.readback)
        changed["size"] = str(len(self.content) + 1)
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_STORAGE_READBACK_SIZE_MISMATCH"):
            self.bind(readback_metadata=changed)

    def test_transition_requires_bound_resolved_digest_and_readback_bytes(self) -> None:
        record = self.bind()
        manifest = {"build_id": self.build_id, "image": self.image, "sbom": record}
        sbom.validate_transition(manifest, self.image, self.build_id, self.content, self.content, self.syft)
        bad = copy.deepcopy(manifest)
        bad["sbom"]["resolved_manifest_digest"] = "sha256:" + "5" * 64
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_RESOLVED_MANIFEST_DIGEST_MISMATCH"):
            sbom.validate_transition(bad, self.image, self.build_id, self.content, self.content, self.syft)
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_CONTENT_JSON_INVALID|SBOM_STORAGE_READBACK"):
            sbom.validate_transition(manifest, self.image, self.build_id, self.content, self.content + b"x", self.syft)

    def test_spdx_shape_is_required(self) -> None:
        invalid = b'{"SPDXID":"SPDXRef-DOCUMENT"}'
        metadata = dict(self.upload)
        metadata["size"] = str(len(invalid))
        with self.assertRaisesRegex(sbom.RepositorySbomError, "SBOM_CONTENT_SPDX"):
            self.bind(content=invalid, readback=invalid, upload=metadata, readback_metadata=metadata)


if __name__ == "__main__":
    unittest.main()

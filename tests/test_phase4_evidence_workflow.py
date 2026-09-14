from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/phase4-evidence-reusable.yml"


class Phase4EvidenceWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def test_provider_native_export_path_is_absent(self) -> None:
        for forbidden in (":exportSBOM", "EXPORT_SBOM", "SBOM_REFERENCE", "cloudStorageLocation"):
            self.assertNotIn(forbidden, self.text)

    def test_existing_vulnerability_and_provenance_reads_remain(self) -> None:
        self.assertIn(
            'collect_occurrences "(kind=\\"DISCOVERY\\" AND resourceUrl=\\"$RESOURCE_URL\\")" '
            'discovery DISCOVERY "$DISC"',
            self.text,
        )
        self.assertIn(
            'collect_occurrences "(kind=\\"VULNERABILITY\\" AND resourceUrl=\\"$RESOURCE_URL\\")" '
            'vulnerability VULNERABILITY "$VULN"',
            self.text,
        )
        self.assertIn(
            'collect_occurrences "(kind=\\"BUILD\\" AND resourceUrl=\\"$RESOURCE_URL\\")" '
            'provenance PROVENANCE "$PROV"',
            self.text,
        )
        self.assertIn("scan-disposition", self.text)
        self.assertIn("provenance-occurrence", self.text)

    def test_repository_generator_is_checksum_verified_before_execution(self) -> None:
        download = self.text.index('"$SYFT_URL" > "$SYFT_ARCHIVE"')
        verify_archive = self.text.index(
            'phase4_repository_sbom.py verify-archive --archive "$SYFT_ARCHIVE"'
        )
        extract = self.text.index('tar -xzf "$SYFT_ARCHIVE" -C "$SYFT_DIR" syft')
        version = self.text.index('"$SYFT_BIN" version > "$SYFT_VERSION"')
        verify_version = self.text.index(
            'phase4_repository_sbom.py verify-version --version-file "$SYFT_VERSION"'
        )
        scan = self.text.index('"$SYFT_BIN" "$IMAGE" \\')
        self.assertLess(download, verify_archive)
        self.assertLess(verify_archive, extract)
        self.assertLess(extract, version)
        self.assertLess(version, verify_version)
        self.assertLess(verify_version, scan)

    def test_generator_uses_only_exact_validated_image_and_existing_token(self) -> None:
        self.assertIn('IMAGE="$(python3 -c', self.text)
        self.assertIn('SYFT_REGISTRY_AUTH_AUTHORITY="us-central1-docker.pkg.dev"', self.text)
        self.assertIn('SYFT_REGISTRY_AUTH_USERNAME="oauth2accesstoken"', self.text)
        self.assertIn('SYFT_REGISTRY_AUTH_PASSWORD="$TOKEN"', self.text)
        self.assertIn('-o "spdx-json=$SBOM_CONTENT"', self.text)
        self.assertIn('-o "syft-json=$SBOM_SYFT_JSON"', self.text)
        self.assertNotIn(":latest", self.text)
        self.assertNotIn("docker build", self.text)
        self.assertNotIn("cloudbuild.googleapis.com/v1/projects/resilio-control-e882d4/builds\"", self.text)

    def test_sbom_and_transition_storage_are_immutable_create_only(self) -> None:
        self.assertEqual(self.text.count("ifGenerationMatch=0"), 2)
        self.assertIn(
            'SBOM_OBJECT="$(python3 scripts/phase4_repository_sbom.py object '
            '--build-id "$BUILD_ID")"',
            self.text,
        )
        self.assertIn('OBJECT="transitions/$BUILD_ID.json"', self.text)
        self.assertIn(
            "https://storage.googleapis.com/upload/storage/v1/b/"
            "resilio-control-e882d4-phase4-evidence/o?uploadType=media&name=",
            self.text,
        )

    def test_transition_revalidates_repository_sbom_binding(self) -> None:
        make_transition = self.text.index("phase4_supply_chain.py make-transition")
        legacy_validate = self.text.index("phase4_supply_chain.py validate-transition")
        repository_validate = self.text.index(
            "phase4_repository_sbom.py validate-transition"
        )
        transition_upload = self.text.rindex(
            "https://storage.googleapis.com/upload/storage/v1/b/"
            "resilio-control-e882d4-phase4-evidence/o?uploadType=media&name="
        )
        self.assertLess(make_transition, legacy_validate)
        self.assertLess(legacy_validate, repository_validate)
        self.assertLess(repository_validate, transition_upload)


    def test_single_syft_scan_emits_spdx_and_native_metadata(self) -> None:
        scan_token = '"$SYFT_BIN" "$IMAGE" \\'
        self.assertEqual(self.text.count(scan_token), 1)
        scan = self.text.index(scan_token)
        spdx = self.text.index('-o "spdx-json=$SBOM_CONTENT"', scan)
        native = self.text.index('-o "syft-json=$SBOM_SYFT_JSON"', scan)
        resolved = self.text.index("phase4_repository_sbom.py verify-resolved-digest", scan)
        upload = self.text.index("upload/storage/v1/b/resilio-control-e882d4-phase4-evidence/o", scan)
        self.assertLess(scan, spdx)
        self.assertLess(spdx, native)
        self.assertLess(native, resolved)
        self.assertLess(resolved, upload)

    def test_generation_specific_readback_precedes_binding_and_transition(self) -> None:
        upload = self.text.index('> "$SBOM_UPLOAD"')
        generation = self.text.index("phase4_repository_sbom.py generation", upload)
        metadata_readback = self.text.index("$ENCODED_SBOM_OBJECT?generation=$SBOM_GENERATION", generation)
        media_readback = self.text.index(
            "$ENCODED_SBOM_OBJECT?generation=$SBOM_GENERATION&alt=media", metadata_readback
        )
        bind = self.text.index("phase4_repository_sbom.py bind", media_readback)
        transition = self.text.index("phase4_supply_chain.py make-transition", bind)
        self.assertLess(upload, generation)
        self.assertLess(generation, metadata_readback)
        self.assertLess(metadata_readback, media_readback)
        self.assertLess(media_readback, bind)
        self.assertLess(bind, transition)

    def test_readback_is_never_latest_object_by_name(self) -> None:
        readback_lines = [
            line for line in self.text.splitlines()
            if "storage.googleapis.com/storage/v1/b/resilio-control-e882d4-phase4-evidence/o/$ENCODED_SBOM_OBJECT" in line
            or "storage.googleapis.com/download/storage/v1/b/resilio-control-e882d4-phase4-evidence/o/$ENCODED_SBOM_OBJECT" in line
        ]
        self.assertEqual(len(readback_lines), 2)
        for line in readback_lines:
            self.assertIn("generation=$SBOM_GENERATION", line)

    def test_bind_and_transition_revalidation_consume_readback_and_syft_metadata(self) -> None:
        for required in (
            '--syft-json "$SBOM_SYFT_JSON"',
            '--upload-metadata-json "$SBOM_UPLOAD"',
            '--readback-metadata-json "$SBOM_READBACK_METADATA"',
            '--readback-file "$SBOM_READBACK_CONTENT"',
        ):
            self.assertIn(required, self.text)
        self.assertGreaterEqual(self.text.count('--readback-file "$SBOM_READBACK_CONTENT"'), 2)


if __name__ == "__main__":
    unittest.main()

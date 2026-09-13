#!/usr/bin/env python3
"""Fail-closed repository-only SBOM binding for Resilio Phase 4."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

CONTROL_PROJECT = "resilio-control-e882d4"
REGION = "us-central1"
ARTIFACT_REPOSITORY = "resilio-phase4"
IMAGE_PACKAGE = "phase4-proof"
IMAGE_PREFIX = f"{REGION}-docker.pkg.dev/{CONTROL_PROJECT}/{ARTIFACT_REPOSITORY}/{IMAGE_PACKAGE}"
EVIDENCE_BUCKET = "resilio-control-e882d4-phase4-evidence"

GENERATOR_NAME = "syft"
GENERATOR_VERSION = "1.51.1"
GENERATOR_ASSET = "syft_1.51.1_linux_amd64.tar.gz"
GENERATOR_URL = (
    "https://github.com/anchore/syft/releases/download/v1.51.1/"
    "syft_1.51.1_linux_amd64.tar.gz"
)
GENERATOR_ARCHIVE_SHA256 = "8fcb33017a0dc1058298c923c436d19dfa68ae93968e0b423248542e3afb9fc3"
GENERATOR_OUTPUT_FORMAT = "spdx-json"

SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
BUILD_ID = re.compile(r"^[0-9a-f-]{8,64}$")
IMAGE_DIGEST_REF = re.compile(rf"^{re.escape(IMAGE_PREFIX)}@sha256:[0-9a-f]{{64}}$")
SYFT_VERSION_LINE = re.compile(r"^Version:\s*1\.51\.1\s*$", re.MULTILINE)


class RepositorySbomError(RuntimeError):
    """Fail-closed Phase 4 repository-SBOM contract violation."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def generator_identity() -> dict[str, str]:
    return {
        "name": GENERATOR_NAME,
        "version": GENERATOR_VERSION,
        "asset": GENERATOR_ASSET,
        "url": GENERATOR_URL,
        "archive_sha256": GENERATOR_ARCHIVE_SHA256,
        "output_format": GENERATOR_OUTPUT_FORMAT,
    }


def require_exact_image(image: str) -> str:
    if not IMAGE_DIGEST_REF.fullmatch(image):
        raise RepositorySbomError("SBOM_IMAGE_DIGEST_INVALID")
    return image


def sbom_object(build_id: str) -> str:
    if not BUILD_ID.fullmatch(build_id):
        raise RepositorySbomError("SBOM_BUILD_ID_INVALID")
    return f"transitions/{build_id}.sbom.spdx.json"


def verify_generator_archive(path: str) -> None:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise RepositorySbomError("SBOM_GENERATOR_ARCHIVE_INVALID")
    if sha256_bytes(candidate.read_bytes()) != GENERATOR_ARCHIVE_SHA256:
        raise RepositorySbomError("SBOM_GENERATOR_CHECKSUM_MISMATCH")


def verify_generator_version(path: str) -> None:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise RepositorySbomError("SBOM_GENERATOR_VERSION_FILE_INVALID")
    text = candidate.read_text(encoding="utf-8")
    if not SYFT_VERSION_LINE.search(text):
        raise RepositorySbomError("SBOM_GENERATOR_VERSION_MISMATCH")


def _validate_spdx_json(content: bytes) -> None:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepositorySbomError("SBOM_CONTENT_JSON_INVALID") from exc
    if not isinstance(payload, dict):
        raise RepositorySbomError("SBOM_CONTENT_SHAPE_INVALID")
    if not str(payload.get("spdxVersion") or "").startswith("SPDX-"):
        raise RepositorySbomError("SBOM_CONTENT_SPDX_VERSION_INVALID")
    if payload.get("SPDXID") != "SPDXRef-DOCUMENT":
        raise RepositorySbomError("SBOM_CONTENT_SPDX_ID_INVALID")


def _storage_identity(build_id: str, metadata: dict[str, Any]) -> tuple[str, str, str]:
    expected_object = sbom_object(build_id)
    if metadata.get("bucket") != EVIDENCE_BUCKET or metadata.get("name") != expected_object:
        raise RepositorySbomError("SBOM_STORAGE_OBJECT_MISMATCH")
    generation = str(metadata.get("generation") or "")
    if not generation.isdigit() or int(generation) <= 0:
        raise RepositorySbomError("SBOM_STORAGE_GENERATION_INVALID")
    return EVIDENCE_BUCKET, expected_object, generation


def _binding_payload(
    image: str,
    location: str,
    generation: str,
    content_sha256: str,
) -> dict[str, Any]:
    return {
        "contract": "resilio-phase4-sbom-binding/v1",
        "image": require_exact_image(image),
        "generator": generator_identity(),
        "location": location,
        "generation": generation,
        "content_sha256": content_sha256,
    }


def bind_repository_sbom(
    image: str,
    build_id: str,
    metadata: dict[str, Any],
    content: bytes,
) -> dict[str, Any]:
    require_exact_image(image)
    _validate_spdx_json(content)
    bucket, object_name, generation = _storage_identity(build_id, metadata)
    content_sha256 = sha256_bytes(content)
    location = f"gs://{bucket}/{object_name}"
    payload = _binding_payload(image, location, generation, content_sha256)
    return {
        "occurrence": f"repository-generator/{GENERATOR_NAME}/{GENERATOR_VERSION}",
        "producer": "repository-generator",
        "generator": generator_identity(),
        "image": image,
        "location": location,
        "generation": generation,
        "sha256": content_sha256,
        "binding_sha256": sha256_bytes(canonical_json_bytes(payload)),
    }


def validate_sbom_record(
    record: dict[str, Any],
    image: str,
    build_id: str,
    content: bytes,
) -> None:
    if not isinstance(record, dict):
        raise RepositorySbomError("SBOM_RECORD_INVALID")
    required = {
        "occurrence", "producer", "generator", "image", "location", "generation", "sha256", "binding_sha256",
    }
    if set(record) != required:
        raise RepositorySbomError("SBOM_RECORD_SHAPE_INVALID")
    if record["occurrence"] != f"repository-generator/{GENERATOR_NAME}/{GENERATOR_VERSION}":
        raise RepositorySbomError("SBOM_OCCURRENCE_INVALID")
    if record["producer"] != "repository-generator":
        raise RepositorySbomError("SBOM_PRODUCER_INVALID")
    if record["generator"] != generator_identity():
        raise RepositorySbomError("SBOM_GENERATOR_IDENTITY_MISMATCH")
    require_exact_image(image)
    if record["image"] != image:
        raise RepositorySbomError("SBOM_IMAGE_MISMATCH")
    expected_location = f"gs://{EVIDENCE_BUCKET}/{sbom_object(build_id)}"
    if record["location"] != expected_location:
        raise RepositorySbomError("SBOM_LOCATION_MISMATCH")
    generation = str(record["generation"])
    if not generation.isdigit() or int(generation) <= 0:
        raise RepositorySbomError("SBOM_STORAGE_GENERATION_INVALID")
    _validate_spdx_json(content)
    content_sha256 = sha256_bytes(content)
    if record["sha256"] != content_sha256:
        raise RepositorySbomError("SBOM_CONTENT_DIGEST_MISMATCH")
    if not SHA256_HEX.fullmatch(str(record["binding_sha256"])):
        raise RepositorySbomError("SBOM_BINDING_DIGEST_INVALID")
    payload = _binding_payload(image, expected_location, generation, content_sha256)
    expected_binding = sha256_bytes(canonical_json_bytes(payload))
    if record["binding_sha256"] != expected_binding:
        raise RepositorySbomError("SBOM_BINDING_DIGEST_MISMATCH")


def validate_transition(
    manifest: dict[str, Any],
    image: str,
    build_id: str,
    content: bytes,
) -> None:
    if not isinstance(manifest, dict):
        raise RepositorySbomError("SBOM_TRANSITION_INVALID")
    if manifest.get("build_id") != build_id:
        raise RepositorySbomError("SBOM_TRANSITION_BUILD_MISMATCH")
    if manifest.get("image") != image:
        raise RepositorySbomError("SBOM_TRANSITION_IMAGE_MISMATCH")
    sbom = manifest.get("sbom")
    validate_sbom_record(sbom, image, build_id, content)


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("generator-spec")
    p = commands.add_parser("verify-archive")
    p.add_argument("--archive", required=True)
    p = commands.add_parser("verify-version")
    p.add_argument("--version-file", required=True)
    p = commands.add_parser("object")
    p.add_argument("--build-id", required=True)
    p = commands.add_parser("bind")
    p.add_argument("--image", required=True)
    p.add_argument("--build-id", required=True)
    p.add_argument("--metadata-json", required=True)
    p.add_argument("--content-file", required=True)
    p.add_argument("--output", required=True)
    p = commands.add_parser("validate-transition")
    p.add_argument("--manifest", required=True)
    p.add_argument("--image", required=True)
    p.add_argument("--build-id", required=True)
    p.add_argument("--content-file", required=True)
    args = parser.parse_args()

    try:
        if args.command == "generator-spec":
            print(canonical_json_bytes(generator_identity()).decode("utf-8"))
        elif args.command == "verify-archive":
            verify_generator_archive(args.archive)
        elif args.command == "verify-version":
            verify_generator_version(args.version_file)
        elif args.command == "object":
            print(sbom_object(args.build_id))
        elif args.command == "bind":
            record = bind_repository_sbom(
                args.image,
                args.build_id,
                _load_json(args.metadata_json),
                Path(args.content_file).read_bytes(),
            )
            Path(args.output).write_bytes(canonical_json_bytes(record) + b"\n")
        else:
            validate_transition(
                _load_json(args.manifest),
                args.image,
                args.build_id,
                Path(args.content_file).read_bytes(),
            )
        return 0
    except (RepositorySbomError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"PHASE4_REPOSITORY_SBOM_STOPPED:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

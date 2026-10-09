"""Pure-local comparison of two explicit canonical deployment observations.

Roles are supplied by the caller, not inferred from time or deployment state.
"""
from __future__ import annotations

from .core import PermanentFailure, event_from_bytes, jcs

_FIELDS = (
    ("change.repository", ("change", "repository")),
    ("change.source_sha", ("change", "source_sha")),
    ("deployment.id", ("deployment", "id")),
    ("deployment.release_id", ("deployment", "release_id")),
    ("deployment.artifact_digest", ("deployment", "artifact_digest")),
    ("deployment.runtime.provider", ("deployment", "runtime", "provider")),
    ("deployment.runtime.kind", ("deployment", "runtime", "kind")),
    ("deployment.runtime.resource_id", ("deployment", "runtime", "resource_id")),
)

_PREFIX = {
    "UNCHANGED": "The baseline and candidate observations have identical canonical payloads. Differing fields: ",
    "CHANGED": "The observations have different logical deployment identities within the same service and environment. Differing fields: ",
    "IDENTITY_CONFLICT": "The observations share a logical deployment identity but have different canonical payloads; this is not evidence of a successful transition. Differing fields: ",
}


def _failure(code: str, role: str) -> PermanentFailure:
    error = PermanentFailure(code)
    error.role = role
    return error


def _event(raw: bytes, role: str):
    if type(raw) is not bytes:
        raise _failure("COMPARISON_INPUT_TYPE_INVALID", role)
    try:
        return event_from_bytes(raw, require_canonical=True)
    except PermanentFailure as error:
        error.role = role
        raise


def _value(observed: dict, path: tuple[str, ...]) -> str:
    for name in path:
        observed = observed[name]
    return observed


def _evidence_key(item: dict) -> tuple[str, str, int, str]:
    return (item["kind"], item["ref"], int("sha256" in item), item.get("sha256", ""))


def compare_deployments(baseline_bytes: bytes, candidate_bytes: bytes) -> bytes:
    """Return one canonical report or raise a role-labelled PermanentFailure."""
    baseline = _event(baseline_bytes, "baseline")
    candidate = _event(candidate_bytes, "candidate")
    before = baseline.observed
    after = candidate.observed
    if (before["service"]["id"] != after["service"]["id"]
            or before["environment"]["id"] != after["environment"]["id"]):
        raise _failure("COMPARISON_CONTEXT_MISMATCH", "comparison")

    if baseline.canonical_bytes == candidate.canonical_bytes:
        classification = "UNCHANGED"
    elif baseline.event_id == candidate.event_id:
        classification = "IDENTITY_CONFLICT"
    else:
        classification = "CHANGED"

    differences = []
    unchanged_fields = []
    for field, path in _FIELDS:
        old, new = _value(before, path), _value(after, path)
        if old == new:
            unchanged_fields.append(field)
        else:
            differences.append({"field": field, "before": old, "after": new})

    before_evidence = {_evidence_key(item): item for item in before["evidence"]}
    after_evidence = {_evidence_key(item): item for item in after["evidence"]}
    evidence_added = [after_evidence[key] for key in sorted(after_evidence.keys() - before_evidence.keys())]
    evidence_removed = [before_evidence[key] for key in sorted(before_evidence.keys() - after_evidence.keys())]

    fields = ", ".join(item["field"] for item in differences) if differences else "none"
    explanation = (
        _PREFIX[classification] + fields
        + ". Supplied evidence references added: " + str(len(evidence_added))
        + "; removed: " + str(len(evidence_removed))
        + ". These references are not independently verified."
    )
    return jcs({
        "contract": "resilio-deployment-change-comparison/v1",
        "scope": "LOCAL_COMPARISON_ONLY",
        "context": {
            "service_id": before["service"]["id"],
            "environment_id": before["environment"]["id"],
        },
        "baseline": {"event_id": baseline.event_id, "payload_sha256": baseline.payload_sha256},
        "candidate": {"event_id": candidate.event_id, "payload_sha256": candidate.payload_sha256},
        "classification": classification,
        "differences": differences,
        "unchanged_fields": unchanged_fields,
        "evidence_added": evidence_added,
        "evidence_removed": evidence_removed,
        "explanation": explanation,
    })

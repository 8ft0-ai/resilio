# Owner-local `agentctl` evidence

This document defines Resilio's first bounded consumer contract for `8ft0-ai/agentctl`. It applies when a governed Resilio task needs owner-local observation or evidence that cannot legitimately be obtained in the remote assistant environment, especially from a private Terraform saved plan.

`agentctl` supplies reusable bounded mechanisms and share-safe evidence. Resilio continues to own policy, expected identities and effects, authority, review gates and the decision about what may happen next.

## Adopted pilot baseline

The exact `agentctl` baseline adopted for this pilot is:

```text
repository: 8ft0-ai/agentctl
commit:     3d0bafa653f9d90349f22b5669fbe05c2a4becb4
tree:       29462eb2e71693f7c26cdbbf67217bacaf4e0392
```

This baseline provides the stable read-only capabilities used or available to this pilot:

```text
python -m agentctl version
python -m agentctl doctor
python -m agentctl repo status [--repo PATH]
python -m agentctl repo evidence [--repo PATH]
python -m agentctl file hash <path>
python -m agentctl file inspect <path>
python -m agentctl github run evidence ...
python -m agentctl terraform plan evidence --plan PATH
```

Each evidence-producing command supports command-level `--json` output. Do not silently substitute a later `agentctl main`, an unmerged branch or a different interface revision. Updating the adopted baseline is a separate Resilio reconciliation/change.

At this baseline `agentctl` requires Python 3.14 or later and has no product runtime dependencies. Resilio does not maintain a separate installer or wrapper. For decision-critical Resilio use, install the exact trusted checkout into its dedicated ignored `.venv` and invoke the supported module entry point through that environment. Do not rely on a bare `agentctl` resolved from ambient `PATH`: at this baseline `agentctl version` reports installed package metadata (`0.0.0`), not the Git commit that supplied the executable.

## Bootstrap the local capability deliberately

Before relying on `agentctl` evidence for a decision-critical Resilio boundary, establish that the local upstream checkout is exactly the adopted source and that the interpreter used for every evidence command imports `agentctl` from that same checkout. A small direct bootstrap check is sufficient; do not download a Resilio helper script merely to run these commands.

For an owner-local checkout path stored in `AGENTCTL_REPO`:

```bash
AGENTCTL_SHA=3d0bafa653f9d90349f22b5669fbe05c2a4becb4
AGENTCTL_PYTHON="$AGENTCTL_REPO/.venv/bin/python"

test "$(git -C "$AGENTCTL_REPO" rev-parse HEAD)" = "$AGENTCTL_SHA"
test -z "$(git -C "$AGENTCTL_REPO" status --porcelain)"

python3.14 -m venv "$AGENTCTL_REPO/.venv"
"$AGENTCTL_PYTHON" -m pip install --disable-pip-version-check --no-deps --editable "$AGENTCTL_REPO"
test -z "$(git -C "$AGENTCTL_REPO" status --porcelain)"

AGENTCTL_REPO="$AGENTCTL_REPO" "$AGENTCTL_PYTHON" - <<'PY'
import os
from pathlib import Path
import agentctl

expected = (
    Path(os.environ["AGENTCTL_REPO"]) / "src" / "agentctl" / "__init__.py"
).resolve()
observed = Path(agentctl.__file__).resolve()
if observed != expected:
    raise SystemExit(f"agentctl source mismatch: {observed}")
PY

"$AGENTCTL_PYTHON" -m agentctl version --json
"$AGENTCTL_PYTHON" -m agentctl doctor --json
"$AGENTCTL_PYTHON" -m agentctl repo evidence --repo "$AGENTCTL_REPO" --json
```

The source-path assertion is the executable/source binding for this pilot: the same interpreter that later produces evidence must import `agentctl` from `src/agentctl` inside the checkout already proven to be at the adopted commit. Stop if the source identity is wrong, the checkout is dirty, the imported package resolves elsewhere, the runtime doctor does not pass, or the bound capability cannot produce share-safe evidence. Do not repair credentials, local cloud configuration or Terraform state from this preflight.

For the Resilio checkout itself, the governing task still supplies the exact expected commit/tree/branch relationship. The bound `agentctl` may observe the checkout but does not decide whether that observation is acceptable:

```bash
"$AGENTCTL_PYTHON" -m agentctl repo evidence --repo "$RESILIO_REPO" --json
```

Compare the returned repository evidence with the exact Resilio identity required by the governing issue or handoff. A clean or dirty observation is evidence; the Resilio task decides whether cleanliness is mandatory.

## Private Terraform saved-plan evidence

Use this path only when a governing Resilio task has already authorised creation or inspection of an existing private saved Terraform plan. This command does not create, refresh, replace or apply a plan:

```bash
"$AGENTCTL_PYTHON" -m agentctl terraform plan evidence --plan "$PLAN" --json
```

The plan remains owner-local/private. At the adopted baseline the capability safely binds to the selected regular file, computes its SHA-256, inspects a verified private snapshot with fixed read-only Terraform commands and emits a deterministic sanitised structural manifest.

For a successful handback, return the complete JSON evidence envelope produced on stdout by the bound invocation without post-processing it through an ad hoc `jq`, Python or shell transformation. The shareable result may contain bounded provenance plus structural resource/output identities, normalised actions/counts, completeness metadata and manifest digests as defined by the adopted `agentctl` contract.

Do **not** return or commit:

- the saved plan itself or its local path;
- raw `terraform show -json` output;
- raw Terraform state or state values;
- `before`, `after`, variable, provider or resource attribute payloads;
- Terraform stderr/private diagnostic material;
- credentials, tokens, billing/account secrets or environment dumps.

If the bound `agentctl` invocation returns unavailable, capability-failure, unsafe-evidence or another non-success status, stop at that observation boundary. Do not fall back to an ambient `agentctl` executable or publish raw Terraform material just to obtain a review object.

## What Resilio still has to decide

A successful `agentctl terraform plan evidence` result proves only that the exact private saved-plan bytes were safely inspected and reduced to the bounded structural manifest. It does not prove that the plan is authorised, safe to apply, policy-compliant or based on the correct Resilio remote state.

The governing Resilio task must continue to establish and review, as applicable:

- exact Resilio repository/main/tree and candidate identity;
- Terraform root, workspace, provider-lock and tool-version expectations;
- authoritative state-domain identity and any required stale-state guard;
- exact allowed resource addresses and action sequences/cardinality;
- forbidden deletes, replacements, permission broadening or unrelated effects;
- expected output changes and any permitted refresh-only drift;
- required genuinely fresh substantive review of the exact saved-plan effect;
- the separate authority and guards for any later apply or external mutation.

Those expectations belong in the Resilio governing issue, plan/review record or another repository-owned policy surface. Do not hard-code them into `agentctl` for reuse convenience.

## Current pilot limits

This pilot intentionally does not recreate capabilities that are not part of the adopted stable baseline.

As of this adoption point:

- Terraform remote-state identity evidence is not adopted here; current upstream work for `agentctl terraform state evidence` is outside this exact baseline until it completes and Resilio separately adopts it.
- Caller-supplied Terraform effect-contract comparison remains a later upstream capability; the exact Resilio effect policy therefore stays in the governing Resilio record/review path for this pilot.
- Broader hermetic repository/tool/workspace/cloud-account preflight remains separately governed upstream; do not replace it with a new large Resilio environment script.
- Bounded multi-step handoff composition is not part of this pilot. Prefer direct named commands over a locally invented orchestration wrapper.

An upstream capability becoming available does not automatically change this contract. Reconcile and adopt it deliberately when a concrete Resilio task benefits from it.

## Promotion and fallback rule

When a future owner-local need appears, first classify it as reusable mechanism or Resilio policy. Reuse an already adopted `agentctl` mechanism where it fits. Keep Resilio-specific expected values, architecture constraints and authority in Resilio. If a generic mechanism is missing, record the concrete consumer evidence upstream rather than copying a substantial implementation into this repository.

A small, bounded one-off command may still be justified when the adopted toolkit genuinely cannot perform the required observation and active governed work cannot wait. That exception does not create a new default: preserve fail-closed guards, keep private diagnostics private, and reconsider promotion if the mechanism recurs.

## Authority boundary

Nothing in this runbook authorises Terraform planning or apply, remote-state mutation, Google Cloud/IAM/resource mutation, workflow dispatch, build execution, evidence writes or deployment. Those actions require their own current Resilio authority and decision-critical evidence.

`agentctl` is an operator substrate. It is not Resilio's authority layer.

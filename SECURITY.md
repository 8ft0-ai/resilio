# Security policy

Resilio is developed in a public repository. Architecture, non-sensitive configuration, policy and deployment definitions should normally be reproducible from public source; security must not depend on hiding safe-to-publish implementation details.

## Reporting a vulnerability

Please avoid publishing exploitable vulnerability details, active credentials, private keys or sensitive operational evidence in a public GitHub issue.

Use GitHub's private vulnerability reporting capability when it is enabled for this repository. If that capability is not available, contact the repository maintainer through a private channel exposed by the maintainer's GitHub profile rather than disclosing the vulnerability publicly.

A vulnerability report should include enough evidence to reproduce and assess the issue without including unrelated sensitive data.

## Secret exposure

A credential or secret committed to this public repository must be treated as compromised even if the commit is later deleted or rewritten.

The response order is:

1. revoke or rotate the affected secret;
2. assess exposure and impact;
3. contain and remediate affected access;
4. remove sensitive history where appropriate; and
5. record the event and corrective action without republishing the secret.

History rewriting is not a substitute for revocation.

## Repository security expectations

- Do not commit secret values, private keys, credentials or private Terraform state.
- Long-lived Google Cloud service-account keys are prohibited by default.
- Prefer federated identity and workload identity over stored credentials.
- Baseline pull-request validation must not require secrets or cloud credentials.
- External automation dependencies should be minimised and immutably pinned when used.
- Workflow permissions should be explicitly least-privilege.
- Security-sensitive changes require substantive review proportional to their authority and blast radius.

See `docs/security-and-private-state.md` for the broader public/private-state model.

## Supported versions

Resilio is currently in an early foundation stage and has not published a stable production release. Security fixes should target the current supported development line unless a later release policy defines additional supported versions.

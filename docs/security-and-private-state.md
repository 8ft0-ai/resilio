# Security and Private State Boundary

## Principle

Resilio is an open-source system. The public repository should contain enough configuration and design information for the reference deployment to be reproducible without depending on secrecy of architecture.

Secret material and sensitive runtime state must live in purpose-built private systems, not in Git.

## Public repository content

The following should normally be public:

- application source;
- Terraform and deployment definitions;
- IAM policy definitions where safe;
- service names and non-sensitive project configuration;
- SLOs and alert definitions;
- resilience experiment definitions;
- schemas;
- runbooks that do not reveal sensitive operational material;
- architecture diagrams and ADRs;
- threat models;
- secret names/references; and
- example/local development configuration without real secret values.

## Private runtime content

The following must remain private where applicable:

- secret values;
- tokens and API keys;
- private keys;
- webhook signing secrets;
- OAuth client secrets;
- sensitive telemetry or user data;
- privileged emergency credentials;
- private Terraform state; and
- any operational evidence whose disclosure would materially increase risk or violate a data-handling requirement.

## Secret-handling hierarchy

Prefer, in order:

1. eliminate the secret through federated identity;
2. use workload identity;
3. use Google Secret Manager for runtime secret material;
4. use GitHub environment secrets only where an external integration requires GitHub to hold a secret; and
5. use long-lived credentials only where unavoidable and explicitly justified.

Long-lived Google Cloud service-account keys are prohibited by default.

## Runtime access

Workloads should obtain secret values directly from Secret Manager using least-privilege workload identity. Deployment workflows should normally deploy references to secrets rather than reading values into GitHub Actions and reinjecting them.

Each workload should receive access only to the secret material it needs.

## Terraform and secrets

Terraform should create and govern secret containers, IAM and lifecycle configuration, but secret payloads should not normally pass through Terraform because provider operations can persist sensitive values in state.

Terraform state must be treated as sensitive operational data even when configuration source is public.

## Local development

Local development should minimise real secret requirements by using emulators, fakes and test doubles.

Where environment files are needed:

```text
.env.example    committed; contains names/placeholders only
.env            ignored
.env.local      ignored
```

No developer-specific credentials should be required to understand or test core product behaviour where a safe emulator is practical.

## Leakage prevention

Defence in depth should include:

- `.gitignore` exclusions for obvious credential/state files;
- local/pre-commit secret scanning where practical;
- GitHub secret scanning and push protection;
- independent CI secret scanning such as Gitleaks; and
- project-specific secret patterns where generic scanners are insufficient.

`.gitignore` is a convenience guard, not the primary security control.

## Secret exposure response

A secret committed to a public repository must be treated as compromised even if the commit is later removed.

The response order is:

1. revoke or rotate the secret;
2. determine exposure and impact;
3. contain and remediate affected access;
4. remove sensitive history where appropriate; and
5. record the security event and corrective actions.

Rewriting Git history is not a substitute for revocation.

## Secret rotation as resilience

Resilio should eventually test its ability to tolerate credential and secret lifecycle events. Rotation, revocation and denied authority are legitimate resilience/security experiment classes.

For integrity-sensitive controls, the expected behaviour may be to fail closed while remaining observable and auditable.

## Break glass

Emergency access must be exceptional, narrowly scoped and auditable. Break-glass material must never be committed to the public repository.

Any emergency runtime mutation should subsequently be reconciled to Git or explicitly reversed so that authorised desired state and actual state do not silently diverge.
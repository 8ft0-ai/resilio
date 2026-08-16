# Git-Driven Engineering Model

## Operating model

Git is the authoritative source of desired state wherever state can reasonably be represented declaratively. GitHub provides the governance and operational-intent plane. Google Cloud is a reconciled runtime target rather than an administration surface.

After bootstrap, routine operation should not require console mutation.

```text
GitHub issue or PR
        |
        v
authorised repository state
        |
        v
automation
        |
        v
Google Cloud runtime
        |
        v
verification and evidence
        |
        +----> GitHub / Resilio
```

Manual cloud changes are break-glass activity. Any legitimate emergency mutation must be auditable and subsequently reconciled back to authorised Git state.

## Monorepo

Resilio should begin as one public monorepo.

A single change may legitimately include application code, infrastructure, an SLO, a resilience experiment, a runbook, an ADR and documentation. Keeping these changes in one repository makes atomic review and traceability possible.

Repository boundaries should only be introduced later where there is a demonstrated need such as an independent release lifecycle, materially different ownership, a security boundary or a genuinely reusable product component.

One repository does not imply one deployment unit or one Terraform state.

## Desired repository shape

The structure should emerge as real artefacts are introduced rather than through empty directory scaffolding. The likely direction is:

```text
.github/
apps/
architecture/
docs/
experiments/
infra/
reference/
reliability/
schemas/
security/
```

## Change lifecycle

The intended normal lifecycle is:

```text
Issue
  |
  v
design/decision where required
  |
  v
bounded implementation
  |
  v
Pull Request
  |
  +-- tests
  +-- security checks
  +-- policy checks
  +-- infrastructure plan
  +-- cost checks
  +-- documentation checks
  |
  v
review
  |
  v
merge
  |
  v
build once
  |
  v
deploy immutable artefact
  |
  v
post-deployment verification
  |
  v
evidence
```

Human review should focus on substantive decisions. Mechanical validation, provisioning, deployment, verification, rollback support, evidence capture and cleanup should be automated wherever it is safe to do so.

## Authority levels

Automation should be proportional to the authority and reversibility of an action.

| Level | Kind of action | Expected control |
|---|---|---|
| 1 | Mechanical validation | Fully automatic |
| 2 | Bounded reversible operation | IssueOps-authorised, then automatic |
| 3 | Persistent desired-state change | PR, review and merge, then automatic |
| 4 | Security or governance boundary | Explicit substantive approval |
| 5 | Break glass | Manual, exceptional and fully audited |

Examples include:

- tests and builds at Level 1;
- running an already approved resilience experiment at Level 2;
- changing infrastructure or experiment definitions at Level 3;
- changing IAM authority or the cost ceiling at Level 4; and
- emergency console mutation at Level 5.

## GitHub and Google Cloud responsibilities

GitHub Actions should own governance and orchestration, including:

- issue and PR control flow;
- validation orchestration;
- policy enforcement;
- release orchestration;
- federated authentication initiation; and
- publishing evidence and status.

Google Cloud services should own trusted build and runtime functions where justified, for example:

- Cloud Build for artefact production, testing, SBOM/provenance and trusted build execution;
- Artifact Registry for immutable artefacts;
- Cloud Deploy for controlled delivery; and
- Terraform for declarative cloud infrastructure.

There should be one clear initiating authority for a release rather than multiple independent systems deciding when deployment occurs.

## Identity and credentials

Long-lived Google Cloud service-account keys are prohibited.

GitHub should authenticate to Google Cloud using OIDC and Workload Identity Federation to obtain short-lived credentials. Runtime workloads should use workload identities and least-privilege IAM.

Agents may propose repository changes, but they should not require persistent cloud administrator credentials. Runtime authority belongs to workflows bound to authorised repository state.

## Secrets and configuration

Public Git should contain:

- source code;
- Terraform and deployment definitions;
- policies;
- SLOs;
- experiment definitions;
- schemas;
- architecture and threat models;
- secret names/references; and
- non-sensitive reference configuration where disclosure is harmless.

Secret values must not be stored in Git.

Preferred secret handling is:

1. federated identity where a secret can be eliminated;
2. workload identity;
3. Google Secret Manager for runtime secret material;
4. GitHub environment secrets only when an external integration requires them; and
5. long-lived credentials only where unavoidable and explicitly justified.

Security should not depend on hiding project IDs, service names or architectural configuration that is safe to publish.

## Terraform state

Terraform state must never be committed to Git.

The canonical deployment should use a private, versioned Google Cloud Storage backend. State is sensitive operational data and should be accessible only to narrowly authorised automation and break-glass administrators.

The monorepo should contain multiple bounded Terraform roots and state domains, initially expected to align approximately with:

```text
foundation
platform
observability
resilience-lab
finops
```

State boundaries should follow lifecycle, authority and blast radius rather than one state per Google Cloud product.

Inter-state dependencies should remain small. Broad use of `terraform_remote_state` should be avoided because read access to state can expose more than the nominal output being consumed.

The state bucket should use private access, object versioning, suitable lifecycle controls and auditability.

## Bootstrap exception

A small, explicit bootstrap phase is required to solve the initial identity/state chicken-and-egg problem.

The bootstrap may create the minimum necessary control resources, such as:

- control/reference projects or their initial bindings;
- required APIs;
- the GCS Terraform backend;
- GitHub workload identity federation;
- bootstrap/deployment identities; and
- initial bounded IAM.

Any temporary local bootstrap state should be migrated to the remote backend immediately and removed after verification.

After bootstrap, the system should be governable through Git and automation alone.

## Drift

Cloud runtime state should be checked periodically against authorised Git state.

Unexpected drift should be surfaced as evidence rather than automatically overwritten without evaluation. The expected flow is:

```text
scheduled reconciliation
       |
       v
Terraform plan / state comparison
       |
       +-- no drift --> record success
       |
       +-- drift -----> open evidence-backed issue
```

A subsequent authorised change may either reconcile the cloud back to Git or formally adopt the runtime change into Git.

## Documentation as code

Documentation should participate in validation. Over time, checks should verify relationships such as:

- service ownership;
- SLO to runbook links;
- alerts to runbooks;
- experiment targets and referenced SLOs;
- ADR references;
- schema examples;
- diagrams and links; and
- compatibility/versioning rules.

Documentation is part of the governed system rather than an after-the-fact narrative.
# Architecture decision records

Use an ADR when a decision establishes or materially changes an architectural, security, authority, cost or lifecycle boundary that future contributors will need to understand.

Do not use ADRs for every implementation detail. Prefer a bounded governing issue or ordinary code/documentation review when the decision is local, reversible and already constrained by accepted architecture.

## Naming

Store accepted records in this directory using a monotonically increasing number and short slug:

```text
0001-short-decision-title.md
```

Numbers identify repository history; they do not imply priority.

## Minimum record

Each ADR should contain:

```markdown
# ADR-NNNN: Title

- Status: proposed | accepted | superseded | rejected
- Date: YYYY-MM-DD
- Governing issue: #N

## Context

What decision is required and which existing constraints matter?

## Decision

What boundary or choice is being established?

## Consequences

What does this enable, constrain, cost or require?

## Evidence and validation

What evidence supports the decision, and what must later implementation verify?
```

## Lifecycle

- A proposed ADR is not implementation authority by itself.
- Accepted ADRs should reference the governing issue/review that authorised the decision.
- Superseding an accepted ADR requires a new governing decision rather than silently rewriting history.
- When an external fact such as cloud pricing materially affects a decision, record it as an implementation-time assumption unless the repository intentionally adopts it as a durable constraint.

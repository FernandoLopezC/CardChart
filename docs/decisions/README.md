# Decision register

These records preserve evidence and expose missing rationale. They do not establish
new behavior. Human decision owners and original decision dates are **unknown**.

| Record | Classification / status | Evidence and boundary |
| --- | --- | --- |
| [0001: Reviewed manifests own membership](0001-reviewed-membership.md) | Documented intent + implemented; draft retrospective, pending owner validation | Product direction, manifest guide, parser/authoring and tests; metadata discovery cannot silently redefine goals |
| [0002: Startup readiness excludes schema migration](0002-startup-readiness.md) | Documented constraint + implemented; draft retrospective, pending owner validation | Repository guidance, factory, synchronization and startup tests; existing columns/data must survive |

No earlier ADRs were found. Existing product documentation establishes intent but
does not identify approvers, alternatives considered or original decision dates.
The historical continuation at commit `f03e1a0` describes an earlier stage and is
not an accepted ADR for the current implementation.

For a consequential ownership, security, consistency, integration, deployment or
recovery change, add a numbered record here. Include status, record type, recording
date, original date/owner (or Unknown), context, decision, alternatives, consequences,
source evidence and open questions. Label proposals separately from observations.
Use a new record to supersede an accepted decision, linking both directions; keep
historical evidence intact. Routine implementation details belong in component guides.

Activation crash/concurrency recovery is a candidate for a future decision, not an
approved design. Its continuation is tracked only in
[remaining tasks](../remaining-tasks.md#establish-activation-recovery-expectations).

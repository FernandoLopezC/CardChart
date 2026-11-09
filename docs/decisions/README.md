# Decision register

- [ADR-0005: scraper retirement, ownership and goal price drops](0005-goal-price-drops.md)
  records the follow-up request and one additive goal-price observation table.

- [ADR-0004: captured guide baselines and FIFO](0004-guide-performance.md) records
  the user's 9 November 2026 approval for three additive Performance tables.

These records preserve evidence and expose missing rationale. They do not establish
new behavior by themselves. Human decision owners and original decision dates for
the retrospective records 0001–0002 are **unknown**. Record 0003 describes the current
reconciliation implementation choice; its accountable human owner is unassigned.

| Record | Classification / status | Evidence and boundary |
| --- | --- | --- |
| [0001: Reviewed manifests own membership](0001-reviewed-membership.md) | Documented intent + implemented; draft retrospective, pending owner validation | Product direction, manifest guide, parser/authoring and tests; metadata discovery cannot silently redefine goals |
| [0002: Startup readiness excludes schema migration](0002-startup-readiness.md) | Documented constraint + implemented; draft retrospective, pending owner validation | Repository guidance, factory, synchronization and startup tests; existing columns/data must survive |
| [0003: Reviewed source reconciliation](0003-reviewed-reconciliation.md) | Current implementation decision, pending owner review | Reconciliation service/routes/tests; dated snapshots and disposals require exact identity, explicit review and repeat-safe ledger records |

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

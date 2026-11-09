# ADR-0002: Limit startup readiness to absent tables and goal synchronization

- **Status:** Draft — retrospective, pending owner validation
- **Record type:** Observed implementation and documented constraint
- **Recorded:** 2026-10-18
- **Original decision date / decision owner:** Unknown / Unknown
- **Inspected revision:** Working tree based on `a0b42ca`; includes pre-existing
  untracked startup tests. [Coverage](../README.md#inspection-baseline-and-existing-documentation).

## Context and observed decision

[Repository instructions](../../AGENTS.md#workflow-and-constraints) prohibit adding
migration code without explicit request. [Product direction](../product-direction.md)
specifies non-destructive creation of an absent database/missing modeled tables,
and keeps structural migration out of scope. This supplies the current constraint;
the original decision discussion and alternatives have not been recovered.

[create_app / ensure_database](../../cardchart/__init__.py#L12-L57) inspect existing
table names, call `db.create_all()` only for missing modeled tables, and synchronize
curated goals. `init-db` repeats that readiness operation. Existing column layouts
are not compared or altered. Goal synchronization commits metadata/entry updates
and adds missing inventory matches while preserving existing ownership records.

## Evidence and consequences

- [Startup tests](../../tests/test_startup.py#L14-L85) exercise an absent SQLite DB
  and a DB with a pre-existing unrelated table/row, checking preservation and goals.
- [Synchronization](../../cardchart/goal_definitions.py#L441-L477),
  [reconciliation](../../cardchart/ownership.py#L18-L67) and
  [goal tests](../../tests/test_goals.py#L119-L241) establish upserts and preservation.

Observed consequence: starting the app or invoking Flask CLI may write the configured
database even when the requested command is validation. This is not read-only schema
validation, backup, migration or recovery. Incompatible existing tables need separately
approved work; these tests do not establish safe conversion of an old schema.

## Alternatives and validation questions

Alternatives historically considered: **not established**. Deployment owner, backup
policy, compatible existing schema inventory and recovery procedure: **unknown**.
Confirm those before defining a production rollout. No migration, deployment change
or new fallback is proposed or authorized by this record.

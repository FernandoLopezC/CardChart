# ADR-0001: Use reviewed manifests as goal membership authority

- **Status:** Draft — retrospective, pending owner validation
- **Record type:** Observed implementation and documented intent
- **Recorded:** 2026-10-18
- **Original decision date / decision owner:** Unknown / Unknown
- **Inspected revision:** Working tree based on `a0b42ca`; includes pre-existing
  untracked manifests and authoring code. [Coverage](../README.md#inspection-baseline-and-existing-documentation).

## Context and observed decision

[Product direction](../product-direction.md) specifies manually curated subsets
and exact accepted printings rather than all printings of a set or Oracle card.
[The existing authoring guide](../goal-manifests.md) explicitly separates discovery
from activation so upstream metadata cannot silently change maintained membership.
This is a documented rationale; original deliberations and approval are unknown.

The system currently loads versioned JSON from `cardchart/goals/`, structurally
validates it into typed definitions, and uses those definitions for synchronization,
quick-update choices, pricing eligibility and purchase defaults. Authoring validates
reviewed metadata against the cached Scryfall snapshot before creating a new manifest.
Startup performs structural validation without a network or bulk-cache requirement.

## Evidence and consequences

- [Manifest loader/parser](../../cardchart/goal_definitions.py#L81-L177) and
  [synchronization](../../cardchart/goal_definitions.py#L441-L477) establish authority
  and stable-key projection; removed DB entries are not automatically deleted.
- [Activation](../../cardchart/goal_authoring.py#L148-L185) establishes conflict checks,
  bulk validation, file creation, registry registration and synchronization.
- [Manifest tests](../../tests/test_goal_manifests.py) cover duplicate printing
  rejection, locked metadata validation and UI/CLI authoring through real code.

Observed consequence: bulk refresh can enrich/validate but does not rewrite maintained
membership. Adding a goal is a reviewed data workflow. Human review and writable
source manifests are operational dependencies; crash-atomic activation is not established.
The detailed ownership editor is an exception to reviewed-version validation, as
documented in [goals](../components/goals.md); this ADR does not claim universal enforcement.

## Alternatives and validation questions

Alternatives historically considered: **not established**. Human validation is
needed for original rationale, owner and date, and whether source-tree activation
is intended for deployments beyond a local app. Do not infer an approved deployment
or recovery design from this implementation.

# Documentation index

Start with the row matching your change, then follow its source and test links.
The guides describe logical ownership; they do not require source folders to match.

| Need | Authority / next stop |
| --- | --- |
| Run CardChart locally | [Root README](../README.md) |
| Understand runtime, startup, dependencies and data boundaries | [Architecture](ARCHITECTURE.md) |
| Change goal membership, authoring, ownership or export | [Goals component](components/goals.md) |
| Change CSV ingestion or inventory identity | [Inventory component](components/inventory.md) |
| Change guide values, conversion or legacy refresh | [Pricing component](components/pricing.md) |
| Understand product intent | [Product direction](product-direction.md) |
| Author a manifest / look up its schema | [Goal manifest authoring](goal-manifests.md) |
| Find architectural provenance | [Decision register](decisions/README.md) |
| Verify a change and choose checks | [Verification runbook](runbooks/verification.md) |
| Continue incomplete work | [Remaining tasks](remaining-tasks.md) |

## One authority per concern

Product direction states intended behavior; the backlog records work, not current
contracts. Component guides route to implementation owners and tests; they do not
replace executable contracts. Reviewed goal JSON owns membership and version data;
the manifest authoring guide owns its human workflow and schema explanation.
Models own persisted shapes; route helpers currently own presentation aggregates.
Use the ownership tables in the guides before adding another rule implementation.

Evidence labels used here:

- **Implemented:** observed in this working tree; tests are cited separately.
- **Intent:** stated in maintained product documentation, not proof of enforcement.
- **Historical:** a dated source or Git revision; never an instruction to restore old behavior.
- **Proposal:** future work, recorded in the existing backlog, not an adopted decision.

## Inspection baseline and existing documentation

Recorded 2026-10-18 against working tree on `main`, based on
`a0b42ca6d87ac5cdd076b66c6901300c7fd32bee`. This includes pre-existing untracked
authoring, ownership, pricing, manifests, UI files, tests and `goal-manifests.md`.
Those inputs were left intact; a checkout of HEAD alone does not reproduce this map.
Human component and decision owners have not been identified.

All current Python modules and tests, configuration names, route callers, manifests,
and relevant templates/JavaScript were inspected (UI inspection was sampled).
No existing ADR directory, docs index, CI configuration, deployment procedure or
standalone handoff collection was found in the repository inventory. Existing
README, product direction, manifest guide and backlog remain in their original
locations and roles. Historical continuation guidance remains available in Git at
`f03e1a08df9203b4100c853680f74ca8fe7770cc:docs/remaining-tasks.md`; its empty-goal
and missing-table observations describe that revision, not current behavior.

No reference repository was supplied. No secrets, local database contents, live
marketplaces, or live Scryfall snapshot were inspected. Historical subset verification
reported in product direction was not repeated. Source citations use relative file
links and inspected line ranges; recheck them when code moves.

## Adoption phases

1. **Completed preparation:** small entry point, component routing, sourced system
   map, two retrospective decision records, verification commands and three change
   walkthroughs. Application files and runtime structure are unchanged.
2. **Human validation:** assign owners, review retrospective rationale and the
   discrepancies in the backlog, and include the pre-existing untracked runtime
   inputs in the appropriate delivery. Resolve behavior changes as separate work.
3. **Future automation, proposed only:** after the documented workflow proves useful,
   consider CI for the existing functional suite and link/anchor checks. Add drift
   checks only for demonstrated recurring errors. No new framework, CI gate,
   source restructuring or automatic documentation enforcement was introduced.

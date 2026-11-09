# Architecture

**Baseline and limitations:** [inspection record](README.md#inspection-baseline-and-existing-documentation),
2026-10-18 working tree. This is an implementation map; decision rationale is
separately classified in the [register](decisions/README.md).

## Runtime and directories

CardChart is one Flask application with a shared SQLAlchemy database and `main`
and `reconciliation` blueprints. [create_app](../cardchart/__init__.py) configures SQLite
under the Flask instance directory, registers routes and CLI commands, then calls
database readiness. There is no worker/queue in the inspected code.
[requirements.txt](../requirements.txt) owns dependencies.

| Location | Responsibility | Change routing |
| --- | --- | --- |
| `cardchart/` Python modules | Application, shared models and workflow logic | Component guides below |
| `cardchart/goals/` | Reviewed, versioned membership data | [Goals](components/goals.md) |
| `cardchart/templates/`, `cardchart/static/` | Server-rendered UI, browser behavior and styles | Follow the workflow's route and guide |
| `tests/` | unittest functional and focused service coverage | [Verification](runbooks/verification.md) |
| `instance/` (Git ignored) | Default SQLite DB, Scryfall/price/FX caches, drafts and candidates | Runtime artifacts; never membership authority |
| `docs/` | Intent, navigation, component contracts, decisions and work queue | [Index](README.md) |

## Logical components and flows

| Component | Owns | Interfaces and dependencies | Guide |
| --- | --- | --- | --- |
| Goals and ownership | Reviewed definitions, checklist projection, ownership links and progress | Manifest parser/registry, authoring UI/CLI, shared models; consumes inventory and bulk metadata | [Goals](components/goals.md) |
| Inventory and ingestion | CSV contract, imported card identity and enrichment | Upload route, importer, Scryfall cache/live API; writes goal matches through reviewed versions | [Inventory](components/inventory.md) |
| Reconciliation | Reviewed source snapshots and disposal ledger | Dedicated CSV workflow, exact printing identities, local Scryfall bulk cache, inventory and goal quantities | [Reconciliation](components/reconciliation.md) |
| Guide and legacy pricing | Bulk price index, EUR/GBP conversion; separate scraper snapshots | Goal/inventory route aggregates, Scryfall cache, Frankfurter; eBay/Cardmarket for explicit legacy refresh | [Pricing](components/pricing.md) |

Startup loads structurally validated manifests into the process registry, creates
absent modeled tables, then upserts goals and reconciles existing inventory.
Authoring reads bulk metadata → creates an inactive draft → accepts human review →
validates and writes a new manifest → registers/synchronizes that goal.
CSV upload resolves metadata → upserts inventory → matches reviewed goal versions →
commits. Reconciliation stages a bounded UTF-8 CSV → maps columns and statuses →
builds an exact-printing preview → atomically updates stock, its transaction ledger
and linked goal quantities. It does not infer absent-card deletions or combine
snapshot counts. Goal/inventory reads build guide values independently of scraper snapshots.
See component guides for source evidence, failure paths and checks.

## Shared data and operational boundary

[models.py](../cardchart/models.py) owns all persisted shapes: `Card` has
legacy `PriceSnapshot` children; `CollectionGoal` has stable-key `GoalCard` entries;
`GoalCardPrinting` records ownership with an optional `Card` link. There is no
inventory allocation ledger: one physical inventory row may satisfy several goals.

[Startup readiness](../cardchart/__init__.py#L47-L57) creates missing tables and
synchronizes goals; it never alters existing columns. Flask CLI commands also
instantiate this app, so even a validation command can write the configured DB.
[ADR-0002](decisions/0002-startup-readiness.md) records this boundary. No production
rollout, backup or disaster-recovery procedure has been verified; `init-db` is not
a repair command for incompatible schemas.

Configuration is set in `create_app`: `SQLALCHEMY_DATABASE_URI`,
`SQLALCHEMY_TRACK_MODIFICATIONS`, `MARKET_PRICING_ENABLED`, and `SECRET_KEY`.
The function's `config` mapping overrides defaults; only `SECRET_KEY` is explicitly
read from the environment. Draft storage also accepts `GOAL_DRAFT_DIRECTORY`
([authoring](../cardchart/goal_authoring.py#L57-L67)). The random secret default is
process-local. There is no authentication or tenant isolation. The reconciliation
blueprint uses a session CSRF token on its POST forms; do not infer general CSRF
protection or multi-user security from
slug-scoped record lookup. The direct [wsgi.py](../cardchart/wsgi.py) script runs
debug mode on all interfaces; this is not a documented production deployment.

## Approved Performance storage

[ADR-0004](decisions/0004-guide-performance.md) authorizes three additional tables:
QuantityLot, GuideObservation and GuideObservationValue. Existing columns and rows
are preserved. [Performance](components/performance.md) owns FIFO reductions, first
valid captured baselines and stored EUR/GBP/FX evidence. Import/reconciliation hooks
share the existing transaction; page reads do not write history. Explicit guide
refresh records an observation after cache publication. No scheduler is introduced.

## Known differences and continuation

The detailed ownership editor is less restrictive than reviewed quick updates;
activation recovery is best effort across file/registry/database state. The guides describe these limits
and [remaining tasks](remaining-tasks.md) holds continuation steps. No source move
is justified by this documentation pass; splitting `routes.py` would need a
separately scoped change with caller and behavior verification.

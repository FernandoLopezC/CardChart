# CardChart UI and pricing implementation handover

Superseded for current behavior by the component guides and [ADR-0005](decisions/0005-goal-price-drops.md). This dated handover remains historical.

Prepared 9 November 2026. This is a dated pickup brief, not a second work queue.
[Remaining tasks](remaining-tasks.md) remains the only active work queue.

## Objective and current state

Implement the preferred mobile/desktop collector interface, improve free GBP
guide pricing, and add meaningful collection performance. Keep collection value
and cost to complete goals as the primary pricing outcomes.

The design study and research are complete enough to plan implementation.
The production redesign, guide refresh fixes and performance storage are **not
implemented**. The user requested this handover; no delivery workflow, branch,
commit, push, PR or production data change was started by preparing it.

Source conversation:
<t3-thread://v2/eebab518-b5b9-4b9f-9c2e-83681ef81291/d231d1b3-30de-403d-b22d-14d6ad464f7f>

Workspace: `F:/workspace/CardChart`, Windows PowerShell. Observed branch: `main`.
Observed HEAD: `adcfa921069c566afffffe4d5abc47f645735553`.
There are substantial pre-existing modified and untracked application, test and
documentation files. A clean checkout of HEAD does **not** reproduce this app.
Inspect `git status --short --untracked-files=all` and the diff before editing.
Preserve inherited work and authorship. Do not reset, clean, discard, or blindly
stage everything. A new checkout needs an explicit transfer of the required dirty
and untracked baseline. Create a task branch before implementation; do not push main.

## User decisions to preserve

- Magic cards, GBP, **free data sources only**. No paid feeds or subscription UI.
- Use the black/teal collector direction and the PP Scheduling guidance already
  adapted into [DESIGN.md](../DESIGN.md): Source Sans 3, readable normal-weight
  text, quiet surfaces, shared controls and details shown when needed.
- The user preferred the second mobile/goal study. The latest performance study
  extends it; do not return to the rejected first concept.
- Home/Overview, Collection, Goals and Performance are the main destinations.
  Preserve import and reviewed reconciliation as separate secondary workflows.
- Binder means a **view inside an existing goal**. Cards and Binder share the
  same curated membership, ownership, totals and export. No named-binder entity.
- Retain the value-over-time chart in Overview and Performance. Its distinctive
  treatment is a warm unfilled line, quiet ticks and a teal square cursor.
  Per-card gain/loss bars supplement the chart; they do not replace it.
- The latest explicit correction is **no slider; inspect by hovering the chart**.
  The study also supports touch and keyboard access. Preserve those alternatives.
- Add increase/decrease since a card was added. The guide-baseline interpretation
  below is a proposal for the concrete implementation plan, not purchase profit.

User preference for the visual direction is established. The latest hover revision
was delivered before this handover request; there is no separate explicit acceptance
of every pixel, metric rule, storage choice or migration.

## Read first and use these artifacts

1. [Repository instructions](../AGENTS.md), [documentation index](README.md),
   [design guidance](../DESIGN.md), [product direction](product-direction.md).
2. [Latest interactive study](../artifacts/design-review-v3/cardchart-performance.html).
   Open this actual file; do not implement from the screenshots alone.
   It includes Overview, Collection, Goals, Cards/Binder, Performance, a detail
   inspector, mobile/desktop switching and hover/touch/keyboard chart inspection.
3. [Latest study evidence](../artifacts/design-review-v3/provenance.json) and
   [preferred earlier layout](../artifacts/design-review-v2/cardchart-mobile-binders.html).
   The font and [SIL licence](../artifacts/design-review-v2/FONT-LICENSE.md) are
   available beside the earlier study. Preserve the licence when self-hosting.
4. [Architecture](ARCHITECTURE.md), then the owning guides:
   [goals](components/goals.md), [inventory](components/inventory.md),
   [pricing](components/pricing.md), [reconciliation](components/reconciliation.md),
   [verification](runbooks/verification.md).

Latest study SHA-256:
`707ffdecde4c8f8041dc6be1a8d7c95c5960b87c3a7a83226b1824eae08659e7`.
Card prices, holdings, baseline dates and daily history in the study are illustrative.
Do not copy its fixture calculations, embedded sample holdings or review toolbar into
production. Its example timeline compares the same 20 holdings at every point;
that is not evidence of historical collection ownership.

## Production ownership map

| Concern | Current owners and gap |
| --- | --- |
| Shared shell | [base.html](../cardchart/templates/base.html), [styles.css](../cardchart/static/styles.css). Current shell has Goals/Inventory/Import/Reconcile; no requested bottom navigation. |
| Overview and Performance | [routes.py](../cardchart/routes.py): `/` currently redirects to `/goals`; neither requested page exists. Add the smallest routes/templates using shared service results. |
| Collection | `inventory()` / `inventory_card_view()` in routes; [index.html](../cardchart/templates/index.html). Preserve search, sort, paging, quantities and full-inventory total. |
| Goals and binder | `goals()` / `goal_detail()` in routes; [goals.html](../cardchart/templates/goals.html), [goal_detail.html](../cardchart/templates/goal_detail.html). Add binder presentation without a new ownership model. |
| Ownership and identity | [models.py](../cardchart/models.py), [ownership.py](../cardchart/ownership.py), [importer.py](../cardchart/importer.py), reviewed [manifests](../cardchart/goals/). One physical inventory row can satisfy multiple goals. |
| Guide prices | [pricing.py](../cardchart/pricing.py): `load_scryfall_price_index`, `load_eur_to_gbp_rate`, `price_for_printing`, `cheapest_price_for_versions`. Route helpers own current aggregates. |
| Bulk refresh | [scryfall_bulk.py](../cardchart/scryfall_bulk.py): `load_bulk_lookup`, `fetch_default_cards_bulk_item`, `download_default_cards`; [goal_cli.py](../cardchart/goal_cli.py) exposes the existing refresh command. |
| Legacy refresh | `refresh_prices()` / `save_best_price()` in routes, [historical scrapers.py](https://github.com/FernandoLopezC/CardChart/blob/dd38ded4f524cc363c0fb0724f1ba03f8272e1db/cardchart/scrapers.py), `PriceSnapshot`. Separate from guide values. |
| Reconciliation | [reconciliation.py](../cardchart/reconciliation.py), [reconciliation_routes.py](../cardchart/reconciliation_routes.py), ledger models. Needed when planning quantity and disposal history. |

The application is Flask/Jinja/SQLAlchemy. Reuse its structure and shared helpers;
no frontend framework, broad source reorganisation or new queue is required by this brief.

## Pricing recommendation and options

**Recommended first delivery:** keep Scryfall EUR guide values converted to GBP
with the existing ECB-based rate service. Repair refresh, finish handling, source
age and coverage before changing providers. This recommendation is not a final
provider-replacement decision.

| Free option | Appropriate use | Limits and decision |
| --- | --- | --- |
| Scryfall bulk + ECB reference FX | Existing exact-printing collection and goal estimates. Lowest integration cost. | Converted European guides are not UK sale prices, condition/grade valuations or delivered checkout totals. Keep as the starting provider. |
| Cardmarket public daily price-guide and product downloads | Compare direct European guide coverage against Scryfall. | Separate from restricted API access. Verify download schema, exact printing/finish mapping, currency, coverage and permitted reuse before selection. Do not silently add a fallback. |
| MTGJSON price files | Evaluate historical card prices and finish coverage if needed for Performance. | `AllPrices` documents 90 days; provider lists distinguish currencies, retail/buylist and normal/foil/etched. Verify chosen provider/currency and identifier mapping. Historical prices cannot reconstruct missing collection lots or quantities. |

Primary references checked during research:
[Scryfall bulk guidance](https://scryfall.com/docs/faqs/i-m-having-trouble-accessing-the-scryfall-api-or-im-blocked-17),
[ECB reference rates](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html),
[Cardmarket public-download announcement](https://news.cardmarket.com/en/Magic/were-making-the-price-guide-and-product-catalogue-available-for-download),
[MTGJSON downloads](https://mtgjson.com/downloads/all-files/),
[price points](https://mtgjson.com/data-models/price/price-points/),
[provider price lists](https://mtgjson.com/data-models/price/price-list/).
Public download availability is distinct from
[Cardmarket API access](https://api.cardmarket.com/ws/documentation/API%3AAuth_Overview).
Scryfall's bulk reference page returned 403 during the handover lookup; the official
guidance and existing integration were available. No live feed payload, coverage
benchmark, scraper markup or reuse permission was validated in this handover.

### Concrete defects and contracts

1. **Refresh mismatch:** the current refresh button runs legacy scrapers, while the
   values users see come from cached Scryfall bulk data. Provide an explicitly named
   guide refresh that updates that pipeline and its cache metadata. Keep legacy
   refresh identifiable and available until its separate retirement decision.
   Test success, unchanged upstream data, timeouts, malformed data and cache failure.
   Do not replace a valid cache with a partial/invalid download. Reads should not
   trigger a full network refresh or per-card scrape.
2. **Legacy EUR labelled GBP:** Cardmarket parsing writes EUR into `price_gbp`.
   Keep those records separate and visibly identify uncertain currency; never
   include them in GBP guide totals or Performance. Preserve old records. Any
   conversion, relabelling/backfill or retirement needs a specific reviewed plan.
3. **Etched handling:** every non-nonfoil finish currently selects `eur_foil`.
   Do not present this as a verified etched price. Test exact finish mapping;
   unsupported exact-finish pricing must be unavailable unless a verified source
   and explicit mapping are selected. No silent USD/ordinary-foil substitution.
4. **Valuation invariants:** inventory uses canonical printing UUID plus finish
   and quantity. Goal owned value includes each accepted positive-quantity printing;
   missing cost uses the cheapest priced accepted version per missing entry.
   Full-scope totals do not change with filtering/pagination. Never sum goal totals
   into collection value because the same inventory may satisfy several goals.
5. **Transparency and failure:** retain Decimal/penny handling, source date, FX date,
   priced coverage and unavailable states. Missing is not zero. A nonempty wholly
   unpriced bucket is unavailable; partial estimates disclose coverage. Current FX
   failure returns no rate, not yesterday's rate; a new fallback is not approved.

## Performance contract to settle before persistence

Recommended meaning: change in guide value for **remaining tracked holdings** since
each quantity lot's first valid guide baseline. This is not purchase profit or
realised return. For comparable lots:

`change = sum((current GBP guide - baseline GBP guide) * remaining quantity)`

`percent = change / sum(baseline GBP guide * remaining quantity) * 100`

Exclude missing current values or baselines from both sides and disclose coverage.
Do not average per-card percentages. A zero denominator has no meaningful percentage.
New copies need their own baseline; disposed copies leave this current-holdings
metric. Historical GBP values must retain the FX evidence used then; changes can
include FX movement.

Example: two copies starting at GBP 10 and now GBP 12 have GBP 4 movement (+20%).
Adding another copy at GBP 12 contributes zero movement at that point, not GBP 12
appreciation. Combined comparable baseline is GBP 32, current GBP 36, change GBP 4
(12.5%). This is a useful regression case.

Before history/schema work, present a concrete proposal covering:

- Baseline/lot fields, exact identity, source and FX timestamps, precision and
  idempotency; where imports, manual quantity edits and reconciliation write them.
- Older inventory and goal-only ownership: start tracking when a valid baseline
  exists, disclose unknown history, and prevent cross-goal double counting.
- Disposal allocation across lots (for example FIFO versus explicit selection),
  corrections and repeat-safe reconciliation. No disposal policy was agreed.
- Snapshot cadence and refresh trigger. Start with the smallest explicit mechanism;
  unattended scheduling is not requested. Never manufacture daily observations.
- Timeline meaning: same-holdings market movement versus historical portfolio value.
  Label quantity additions/disposals if using portfolio value. Do not compare a
  changing population as though it were pure market movement. Period change and
  since-added change have different baselines and must be labelled separately.
- Minimum usable history and honest empty/single-point states; no synthetic trend
  or reconstructed holding history from `Card.created_at` or legacy snapshots.
- Additive storage/migration, backup/recovery and existing-database compatibility.
  `create_all()` creates missing tables but does not alter existing columns.

The repository forbids unrequested migration and fallback work. The current request
is a handover, so it grants neither. Obtain explicit approval for the concrete
schema/migration or new fallback plan when necessary; continue independent UI and
current-guide work within the next task's authorization. Do not call the whole
implementation complete if the requested Performance history remains blocked.

## Suggested delivery sequence

1. Reconcile the actual dirty working tree with this brief. Read the source and
   tests, establish inherited ownership, and present the concrete implementation
   plan with the history decisions above. Treat this handover as context, not proof.
2. Stabilise current guide refresh and data contracts. Agree a shared presentation
   shape for value, coverage, source/FX dates and unavailable states.
3. Implement the shared shell and one representative phone view. Then carry the
   design into Collection, Goals, Cards/Binder and inspectors. Preserve operational
   workflows and do not expose the prototype's review controls.
4. Implement agreed history storage and transaction integration, then Overview and
   Performance queries and charts. Wire real data only; show explicit empty states
   until enough recorded data exists.
5. Prove real workflows, complete the full offline suite on the integrated state,
   update owning guides/decisions/remaining tasks, and run the requested delivery
   review workflow. Leave an open, unmerged PR under full-stop.

Act as orchestrator, using at most two workers. Give each changed file one owner;
the parent owns contracts, integration and final evidence. Pricing/history and
presentation can proceed independently after their contract is agreed. Do not
split overlapping edits to `routes.py` between workers without serial integration.

## Success criteria

| ID | Observable acceptance condition |
| --- | --- |
| UI-1 | Real Overview, Collection, Goals and Performance pages follow the latest study and DESIGN.md. Import, reconciliation, authoring, export and detailed editing remain reachable. |
| UI-2 | At 360, 390 and 430px, no page-level horizontal overflow or covered controls. Bottom navigation is labelled, has at least 44px targets and safe-area clearance. Desktop uses available width. |
| UI-3 | Cards/Binder switch within one goal. Stable manifest order, missing pockets, explicit paging, filters, quantities, accepted versions and full-goal Wants List export remain correct. |
| UI-4 | The chart remains visible where history permits; no separate range slider exists. Hover/tap selects the correct nearest snapshot at phone and desktop sizes; arrows/Home/End work with visible focus. Date and GBP value agree. |
| UI-5 | Empty, loading, error, stale, unavailable and partial states are truthful. Long names, enlarged text, reduced motion, inspector Close/Escape, focus return and scroll restoration work. |
| PRICE-1 | Guide refresh visibly affects the displayed guide pipeline and reports source age/outcome. Legacy scraper refresh is separate. Failed refresh cannot corrupt the last valid cache or claim success. |
| PRICE-2 | Exact printing/finish, quantity, rounding and accepted-version rules are tested. Unsupported etched and unknown prices remain unavailable. No legacy EUR enters a GBP total. |
| PRICE-3 | Inventory and goal totals are independent of paging/filtering; collection value never sums overlapping goals. Coverage/source/FX dates are available; goal cost excludes shipping/fees and is labelled an estimate. |
| PERF-1 | Approved persistence records first valid per-addition baselines and subsequent observations with source/FX evidence. Old holdings never receive fabricated historical values. Restarts retain history. |
| PERF-2 | Tests cover mixed quantities, new copies, partial disposals, repeated imports/disposals, missing current/baseline data and zero baseline. Additions are not appreciation; disposed quantities follow the agreed rule. |
| PERF-3 | Aggregate percentage uses comparable combined baseline. Mover filters do not change headline scope. Period and since-added metrics are distinguished, and chart points match the chosen holdings/time contract. |
| SAFE-1 | Existing collection data, accepted printings, notes, acquisition dates and inventory links survive. Quick-update behavior is not silently changed: it can currently zero other printings or remove links. Any changed semantics receive explicit scope and regression coverage. |
| DONE-1 | Focused tests and the complete configured offline suite pass on the final integrated state. Real-app desktop/mobile workflows and failure states are observed; mockup checks alone are insufficient. |
| DONE-2 | Required review/CI findings are resolved on the final head. Documentation and the single work queue reflect reality. Full-stop leaves the PR open, unmerged, with auto-merge/merge queue disabled and a clear ready/waiting/blocked verdict. |

## Verification and inherited evidence

The latest mockup revision passed 28 interaction assertions, with preview inspection
at 360/390/1280px. The checks include pointer and keyboard events; touch was synthetic,
not a physical-phone test. The existing offline suites passed 69 Python and 9 Node
tests during that revision. Logs: [Python](../artifacts/design-review-v3/python-tests.log),
[Node](../artifacts/design-review-v3/node-tests.log). An existing SQLAlchemy
`Query.get()` deprecation warning remains. [Earlier provenance](../artifacts/design-review-v2/provenance.json)
identifies the tested application/test source hashes and HEAD; latest provenance
identifies the mockup hash. Recheck scope before reusing any result after changes.

No production UI, live-price payload, data migration, full accessibility audit or
physical device was proven by this design work. The static detector's assumed-white
host caused one contrast warning; dark mobile/desktop renders were inspected.
The handover itself only requires documentation/source checks, not another app-suite run.

Use the [verification runbook](runbooks/verification.md). On this Windows environment:

```powershell
Set-Location F:/workspace/CardChart
New-Item -ItemType Directory -Force .venv/context-check-tmp | Out-Null
$env:TEMP = (Resolve-Path .venv/context-check-tmp).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m unittest discover -s tests
node --test tests/*.test.cjs
.\.venv\Scripts\python.exe -m compileall -q cardchart
git diff --check
```

Check each command's result; a later success must not hide an earlier failure.
Use one owner for the final suite; rerun it after relevant final changes.
Use isolated test databases for runtime/browser proof. Flask app/CLI startup can
create tables and synchronize goals, so do not point tests at the real collection.
Reproduce refresh outcomes and pricing failures with real service paths, plus a
bounded permitted live-provider check if the integration contract changes.

## Copyable pickup and delivery command

This is a prompt for the **new agent**, not a workflow executed by this handover.
Current harness instructions and installed skill versions take precedence.

```text
Pickup from F:/workspace/CardChart/docs/implementation-handover.md.

Use $full-stop to deliver the CardChart UI, free GBP pricing improvements and
Performance work against the handover's success criteria. Act as orchestrator
and follow AGENTS.md, using at most two workers with clear file ownership.

First reconcile the dirty working tree and present the concrete implementation
plan. Resolve the history/lot/FX/disposal and migration decision gates before
dependent changes. Preserve inherited work, collection data and legacy pricing.
Do not reopen settled visual choices: use the latest v3 study, goal Cards/Binder,
and the distinctive line chart with hover inspection and no slider.

Run focused checks, the final offline suite, and real-app mobile/desktop proof.
Use the full-stop review and PR workflow; update the owning docs and work queue.
Leave the PR open and unmerged, with no auto-merge or merge queue. Report the PR
link, final head, success-criteria evidence and any unresolved blocker.
```

Full-stop means finish, prove, review, file/update and monitor the PR, then stop
before merging. It follows the installed full-send workflow with its merge
permission overridden. In this setup it uses one `sol-loop` review workflow,
then `file-pr` and `babysit-pr`; do not add a competing review loop. Verify current
skill paths from the next session's catalog. On T3, use the native PR watcher
and GitHub tools, not a Unix-only watcher script; unwatch before handoff. Do not
merge, enable auto-merge, enter a merge queue, push main or bypass protections.

Full-stop reference read for this brief:
`C:/Users/VastoLorde/.codex/skills/full-stop/SKILL.md`.
Reading its full-send dependency did not invoke either delivery workflow here.

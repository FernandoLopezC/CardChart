# Collector UI, GBP guides and Performance proof

Observed on 9 November 2026 with Python 3 / repository `.venv`, Node, and installed
Chrome controlled by Playwright on Windows. All browser data is synthetic and lives
in an isolated SQLite database. No production collection was opened or migrated.
Source hashes are in `tested-files.json`; logs retain full offline-suite output.

| Criteria | Evidence |
| --- | --- |
| UI-1/2 | Nine actual routes at 360, 390, 430 and 1280px: Overview, Performance, Collection, Goals, Binder, card detail, authoring, upload and reconciliation. No page overflow; labelled mobile navigation targets at least 44px. `browser-precheck.json`. |
| UI-3 | Goal route tests cover stable nine-pocket order, filter highlighting, view-switch position and full Wants List export; existing 28 goal tests retain quantity/value coverage. |
| UI-4 | Persisted observations inspected by hover, synthetic touch and arrows/Home/End at all four widths. Date/GBP agree; warm unfilled line and square cursor; no range slider. `history-browser.json`, desktop/phone screenshots. |
| UI-5 | Dialog Escape, focus/scroll return, failed artwork, enlarged-text reflow, reduced-motion configuration, truthful empty/partial states and refresh failures exercised. |
| PRICE-1/2/3 | Ten pricing, seven bulk-cache and four route tests cover exact finish, unavailable/zero prices, rounding, atomic cache publication, refresh CSRF/failure, unchanged evidence and overlapping goals. Bounded live metadata/FX GETs returned HTTP 200; no live full-bulk download. |
| PERF-1/2 | Ten service tests cover additions, weighted baselines, FIFO, repeated imports/disposals, missing evidence, zero denominator, rollback and backup/reopen with preserved notes/links/legacy data. Browser restart retained three observations and 25 lots before further capture. |
| PERF-3 | Mixed lots: two copies at £10, then one at £12, current £12 gives £4 / £32 = 12.50%. Mover filters leave headline unchanged. Chart records portfolio quantity changes separately. |
| SAFE-1 | Existing seven model declarations unchanged; exactly three models added. Original 77 dirty/untracked files backed up and hashed locally before edits. Existing collection DB untouched. Native ownership semantics retained and disclosed. |
| DONE-1 | Final `python -m unittest discover -s tests`: 91 passed. `node --test tests/*.test.cjs`: 13 passed. Compileall and whitespace checks passed. Browser: 42 layout/workflow checks, 10 grouped history/refresh checks, five transaction checks. |
| DONE-2 | Independent Sol review and PR readiness follow this candidate. See the current work queue and PR for final verdict. |

The five real mobile transaction checks upload/map/review/apply a snapshot, repeat
the snapshot, apply a disposal, reject its repeat, and inspect the resulting chart.
Stock stays unchanged during review. Additions create one lot, repeated absolute
counts create none, and a disposal consumes the oldest remaining lot.

The first preview tool timed out twice. Validation then used local Playwright and
Chrome. Playwright was installed only in `.venv`; no runtime dependency was added.
The Impeccable detector reported an inherited Arial declaration; actual collector
renders use Source Sans 3. Real renders drove corrections to chart fill, currency,
failed images, panel contrast and goal header density.

Screenshots show fixture values, generic local card artwork and synthetic history.
Touch events are automated; physical phones and full screen-reader certification
were not tested. Legacy marketplace scraping was preserved, not live-tested. Old
cache generations remain on disk. Back up the database before production startup;
see [Performance recovery](../../docs/components/performance.md).

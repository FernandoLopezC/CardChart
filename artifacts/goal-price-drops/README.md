# Goal price-drop delivery evidence

Recorded 9 November 2026 against the source/test hashes in [tested-files.json](tested-files.json).
The change retires scraper execution, keeps Scryfall bulk downloads and archived
prices, aligns reviewed ownership with valuation, and flags missing-card guide drops.

- `python -m unittest discover -s tests`: 106 passed.
- `node --test tests/*.test.cjs`: 13 passed.
- `python -m compileall -q cardchart` and `git diff --check`: passed.
- Six grouped real-app Chrome checks passed at 390px and 1280px: refresh captures
  a missing-card comparison; Cards filter and inspector amounts/focus; Binder
  stable pockets and exact highlighted card; ownership save removes its flag.
- The real Flask routes/services ran with isolated SQLite and fixture Scryfall/FX
  inputs. No production database, live download or physical device was exercised.

Independent implementation review identified case-sensitive duplicate ownership.
The fix normalizes editor, quick-save, import and valuation comparisons. A regression
checks mixed-case legacy records cannot inflate value. UI inspection identified
dimmed Binder labels; only nonmatching artwork now dims.

The first full suite failed during Windows SQLite backup-test cleanup. Closing
the backup connection fixed the failure; the focused tests and full suite then
passed. Browser checks also passed after the bounded layout corrections.

Full local logs, task-only diff and screenshots remain in
`.orchestration/goal-price-drops/`. This report makes the recorded scope available
in the repository; the shipped tests can be rerun with the commands above.

Back up the configured SQLite database before first startup. The feature adds one
goal-price observation table through existing startup and preserves old records.
Comparison starts with captured prices, not fabricated history. No scheduled
refresh, email notification or import redesign is included.

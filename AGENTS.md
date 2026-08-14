# Repository guidance

Before changing code, read `README.md`, `docs/product-direction.md`, `docs/remaining-tasks.md`, and any relevant documentation under `docs/`.

- Treat maintained documentation as the source of truth for product intent, architecture, and planned work. Call out discrepancies with implementation instead of silently choosing one.
- Update documentation when behavior, architecture, data structures, routes, setup, or remaining work changes.
- Never add database migration code or new fallback behavior unless explicitly requested.
- Keep implementation and documentation human-readable and concise.
- Run relevant checks before completing work. Never claim a test or manual verification that was not performed.
- Keep `docs/remaining-tasks.md` current: remove completed work and record newly discovered work.

Every completion handoff must cover what and why the work changed, affected components, tests and checks, decisions and assumptions, remaining work, known risks or blockers, upstream dependencies, and downstream effects.

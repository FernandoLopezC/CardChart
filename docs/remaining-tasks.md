# Remaining tasks

Completed implementation is reflected in the product documentation and code rather than retained here as unfinished work.

## Verify and populate curated membership

- **Status:** Blocked in the hosted environment; ready to continue locally
- **Reason:** Scryfall's official API could not be reached from the development environment, so precise subset membership and canonical printing UUIDs were not verified and were not guessed.
- **Required work:** Verify the Classic Artist and Japanese Mystical Archive subsets against official Scryfall data, then add only confirmed ordered entries and accepted UUIDs to `goal_definitions.py`.
- **Upstream dependencies:** Access to Scryfall's official API or set pages.
- **Downstream effects:** Goals currently initialize with zero checklist entries; verified definitions will enable useful progress and explicit import matching.
- **Risks or constraints:** Set or name matching is not an acceptable substitute for canonical UUID verification.

### Local continuation handoff

A local Codex or ChatGPT coding session can continue this task when the computer can reach `https://api.scryfall.com`. Start the session in the repository and ask it to read `AGENTS.md`, `README.md`, `docs/product-direction.md`, and this file before editing anything.

First confirm access without changing the repository:

```bash
python - <<'PY'
import requests

headers = {
    "User-Agent": "CardChart/0.1 (+local collection tracker)",
    "Accept": "application/json",
}

for set_code in ("hoc", "soa"):
    response = requests.get(
        f"https://api.scryfall.com/sets/{set_code}",
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    print(data["code"], data["name"], data["card_count"])
PY
```

Then direct the local coding session to:

1. Retrieve all pages for `set:hoc` and `set:soa` from Scryfall's official card search API.
2. Inspect official metadata to identify the requested Classic Artist and Japanese Mystical Archive subsets.
3. Stop and document the ambiguity if the metadata does not identify either subset reliably.
4. Add only verified ordered entries and canonical printing UUIDs to `cardchart/goal_definitions.py`; do not make every card in either set a goal member.
5. Update tests and this file, run the full test suite, `python -m compileall cardchart`, and `git diff --check`, then report exactly what was verified.

## Decide the future of legacy pricing

- **Status:** Pending decision
- **Reason:** Pricing is no longer the primary product direction, but its removal has not been approved.
- **Required work:** Decide whether and when to retire price snapshots, scrapers, and refresh routes.
- **Upstream dependencies:** Product-owner approval and a data-retention decision.
- **Downstream effects:** A future decision may simplify inventory and card-detail views.
- **Risks or constraints:** Existing pricing data and behavior must remain intact until approval.

## Existing database rollout

- **Status:** Pending deployment work
- **Reason:** This change intentionally includes no database migration code.
- **Required work:** Define an approved, non-destructive rollout for existing databases before deployment; fresh databases can use `init-db`.
- **Upstream dependencies:** Deployment and data-backup policy.
- **Downstream effects:** Existing installations cannot use goal tables until their schema is updated externally.
- **Risks or constraints:** Preserve all imported cards and price snapshots; do not apply destructive schema operations.

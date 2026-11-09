# Goal manifest authoring

CardChart loads maintained collection goals from `cardchart/goals/*.json`. A manifest is the reviewed source of truth for checklist membership, version dropdowns, pricing eligibility, and Cardmarket Wants List mappings.

Refreshing Scryfall data never edits a maintained manifest. Candidate discovery and activation are separate so an upstream metadata change cannot silently add, remove, or substitute a printing.

## In-app workflow

1. Open **Goals**, then select **Add goal**.
2. Refresh or download the Scryfall bulk snapshot from the setup screen when needed.
3. Enter the goal title, stable slug, and description. Search the set dropdown by name or code and choose a language.
4. The live gallery loads automatically. Treatment chips section the candidates using public Scryfall bulk metadata; toggle them to change what is visible, then include or exclude individual cards. **Select visible**, **Deselect visible**, **Show selected only**, the selected count, and the compact selection strip make the submitted membership explicit.
5. If needed, use **Advanced filters** for numeric collector bounds or one exact `field=value` expression per line. Cardmarket expansion and version must either both be supplied or both be blank. If submission fails validation, the reloaded gallery restores the submitted card selection, including an empty selection, instead of selecting every card again.
6. Select **Review selected cards**. CardChart submits the exact selected entry keys, searches only the local bulk snapshot, stores an inactive draft, and groups accepted printings by Oracle ID.
7. On the review screen, exclude unwanted versions and correct the card names, treatment notes, and version labels. When Cardmarket export is configured, choose one included Wants List default per entry.
8. Select **Validate and create goal**. CardChart checks the complete manifest and exact Scryfall metadata, refuses conflicts, writes a new file under `cardchart/goals/`, synchronizes the new goal, checks the existing collection for accepted printing-and-finish matches, and opens it immediately with those entries already owned.

Treatment groups are explanatory filters rather than a substitute for review. They currently recognize specific promo tags such as `sourcematerial`, `surgefoil`, `silverscroll`, `poster`, textured/special foils, serialized, headliner, bundle, Buy-a-Box, and prerelease; frame and presentation fields add Showcase, Extended art, Borderless, Full art, and Etched foil. Umbrella tags such as `universesbeyond` and `boosterfun` are not shown as treatments. A card can appear in more than one group. When Scryfall does not expose a website section name in its public card object, CardChart does not guess or scrape it; use the visible metadata groups, collector bounds, or an exact advanced filter and confirm the final versions on step two.

Drafts live under `instance/goal-drafts/` and are not loaded as goals. **Discard draft** removes an inactive draft. The new-goal workflow never edits or replaces an existing maintained manifest, even when a slug is reused. The application process therefore needs write access to `cardchart/goals/` for activation.

## CLI workflow

1. Refresh the local compressed `default_cards` snapshot:

   ```bash
   flask --app cardchart goals refresh-bulk
   ```

2. Scaffold a broad candidate into the Flask instance directory:

   ```bash
   flask --app cardchart goals scaffold --slug hobbit-book-covers --title "The Hobbit Book Covers" --description "The complete book-cover treatment." --set-code hoc --language en
   ```

   Narrow numeric subsets with `--collector-from` and `--collector-to`. Repeat `--filter FIELD=VALUE` to require scalar or list metadata from the bulk record, for example `--filter frame_effects=showcase` or `--filter promo_types=boosterfun`. Scaffolding considers paper cards only and groups selected printings with the same Oracle ID into one checklist entry. An existing output file is refused without changing its contents, including when `--output` is supplied. Use a new `--output` path when generating another candidate.

3. Review the generated file under `instance/goal-candidates/`. Confirm:

   - every entry belongs in the requested subset and appears in the intended order;
   - every version has the exact Scryfall UUID, set, collector number, language, and finish;
   - labels describe the real treatment rather than the scaffold's generic finish label;
   - the entry image represents the intended version;
   - one purchase-list default is declared per entry when Cardmarket export is enabled;
   - Cardmarket expansion and version names match Cardmarket's decklist notation.

4. Validate the reviewed candidate against the cached bulk snapshot:

   ```bash
   flask --app cardchart goals validate instance/goal-candidates/hobbit-book-covers.json
   ```

5. Move the reviewed file into `cardchart/goals/`, then validate all maintained manifests and restart CardChart:

   ```bash
   flask --app cardchart goals validate
   flask --app cardchart init-db
   ```

`goals validate --structure-only` is available for structural checks when no bulk cache exists. Activation still requires a prior bulk-backed review; startup intentionally does not require network or bulk-cache access.

## Schema

```json
{
  "schema_version": 1,
  "position": 100,
  "slug": "example-goal",
  "title": "Example Goal",
  "description": "A curated subset.",
  "defaults": {
    "set_code": "abc",
    "language": "en"
  },
  "image_url": "https://cards.scryfall.io/...",
  "cardmarket": {
    "expansion": "Expansion Name",
    "default_version": "V.1",
    "wants_list_version_key": "nonfoil"
  },
  "entries": [
    {
      "key": "abc-1",
      "name": "Example Card",
      "oracle_id": "00000000-0000-4000-8000-000000000000",
      "collector_number": "1",
      "treatment": "Book-cover treatment",
      "image_url": "https://cards.scryfall.io/...",
      "versions": [
        {
          "key": "nonfoil",
          "label": "Non-foil",
          "scryfall_id": "11111111-1111-4111-8111-111111111111",
          "collector_number": "1",
          "finish": "nonfoil"
        },
        {
          "key": "special",
          "label": "Special foil",
          "scryfall_id": "22222222-2222-4222-8222-222222222222",
          "set_code": "xyz",
          "collector_number": "50",
          "finish": "foil",
          "language": "en",
          "cardmarket_expansion": "Alternate Expansion",
          "cardmarket_version": "V.2"
        }
      ]
    }
  ]
}
```

`schema_version`, `slug`, `title`, `description`, and a non-empty `entries` array are required. Every entry requires a stable key, name, and at least one explicit version. Every version requires a unique key within the entry, a Scryfall UUID, collector number, finish, language, and set code; entry and goal defaults can supply the latter fields.

A Scryfall printing may expose more than one finish, so the same UUID may appear more than once within an entry when the finish differs. A UUID cannot belong to two different entries in the same goal. Goals may contain versions from multiple sets by overriding `set_code` on an entry or version.

For Cardmarket export, the goal-level `wants_list_version_key` selects the same version key from every entry. If entries use different keys, omit that setting and mark one version per entry with `"wants_list_default": true`. `cardmarket_expansion` and `cardmarket_version` on a version override the goal-level mapping.

## Synchronization behavior

All maintained manifests are parsed and validated before database synchronization begins. Synchronization creates or updates goal metadata and checklist entries by stable key while preserving existing ownership records. It also links positive-quantity inventory rows to missing goal ownership records only when the canonical Scryfall printing UUID and finish match a reviewed version exactly. Finish-suffixed inventory IDs retain their canonical UUID for this comparison. Card names, Oracle IDs, and other printings are not substitutes, while one inventory printing may satisfy matching entries in more than one goal. It does not migrate columns, remove tables, infer alternate membership, overwrite ownership records, or automatically delete database entries that were removed from a manifest.

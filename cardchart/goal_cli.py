import json
from pathlib import Path

import click
from flask import current_app
from flask.cli import with_appcontext

from .goal_authoring import (
    build_candidate_manifest,
    candidate_cards,
    parse_filter,
    validate_definitions_against_bulk,
)
from .goal_definitions import (
    MANIFEST_DIRECTORY,
    GoalManifestError,
    load_goal_manifest,
    load_goal_manifests,
    parse_goal_manifest,
)
from .scryfall_bulk import load_bulk_lookup


def register_goal_commands(app):
    app.cli.add_command(goals_cli)


@click.group("goals")
def goals_cli():
    """Create and validate curated goal manifests."""


@goals_cli.command("refresh-bulk")
@with_appcontext
def refresh_bulk_command():
    """Refresh the local Scryfall default_cards bulk snapshot."""
    lookup = load_bulk_lookup(refresh=True)
    click.echo(f"Scryfall bulk cache is ready with {len(lookup.cards)} cards.")


@goals_cli.command("validate")
@click.argument(
    "manifest",
    required=False,
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
)
@click.option(
    "--structure-only",
    is_flag=True,
    help="Skip checks against the locally cached Scryfall bulk data.",
)
@with_appcontext
def validate_goal_command(manifest, structure_only):
    """Validate one candidate or every maintained goal manifest."""
    try:
        definitions = (
            (load_goal_manifest(manifest),)
            if manifest
            else load_goal_manifests(MANIFEST_DIRECTORY)
        )
    except GoalManifestError as exc:
        raise click.ClickException(str(exc)) from exc

    if not structure_only:
        lookup = load_bulk_lookup(refresh=False)
        if lookup is None:
            raise click.ClickException(
                "No local Scryfall bulk cache exists. Run "
                "'flask --app cardchart goals refresh-bulk' first, or use "
                "--structure-only."
            )
        errors = validate_definitions_against_bulk(definitions, lookup)
        if errors:
            message = "Scryfall validation failed:\n" + "\n".join(
                f"- {error}" for error in errors
            )
            raise click.ClickException(message)

    entry_count = sum(len(definition.entries) for definition in definitions)
    qualifier = " structurally" if structure_only else " against Scryfall bulk data"
    click.echo(
        f"Validated {len(definitions)} goal manifest(s) and "
        f"{entry_count} entries{qualifier}."
    )


@goals_cli.command("scaffold")
@click.option("--slug", required=True, help="Stable lowercase goal slug.")
@click.option("--title", required=True, help="Goal title shown in the UI.")
@click.option("--description", required=True, help="Short goal description.")
@click.option("--set-code", required=True, help="Scryfall set code to inspect.")
@click.option("--language", default="en", show_default=True)
@click.option("--collector-from", type=int)
@click.option("--collector-to", type=int)
@click.option(
    "filters",
    "--filter",
    multiple=True,
    metavar="FIELD=VALUE",
    help="Require a Scryfall field value; repeat for multiple fields.",
)
@click.option("--cardmarket-expansion")
@click.option("--cardmarket-version")
@click.option(
    "--output",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Candidate output path; defaults under the Flask instance directory.",
)
@with_appcontext
def scaffold_goal_command(
    slug,
    title,
    description,
    set_code,
    language,
    collector_from,
    collector_to,
    filters,
    cardmarket_expansion,
    cardmarket_version,
    output,
):
    """Create a reviewable candidate from the local Scryfall bulk cache."""
    if (cardmarket_expansion is None) != (cardmarket_version is None):
        raise click.ClickException(
            "Provide both --cardmarket-expansion and --cardmarket-version, or neither."
        )
    if (
        collector_from is not None
        and collector_to is not None
        and collector_from > collector_to
    ):
        raise click.ClickException("--collector-from cannot exceed --collector-to.")

    try:
        parsed_filters = tuple(parse_filter(value) for value in filters)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    lookup = load_bulk_lookup(refresh=False)
    if lookup is None:
        raise click.ClickException(
            "No local Scryfall bulk cache exists. Run "
            "'flask --app cardchart goals refresh-bulk' first."
        )

    candidates = candidate_cards(
        lookup,
        set_code=set_code,
        language=language,
        collector_from=collector_from,
        collector_to=collector_to,
        filters=parsed_filters,
    )
    if not candidates:
        raise click.ClickException("No Scryfall bulk cards matched those filters.")

    manifest = build_candidate_manifest(
        slug=slug,
        title=title,
        description=description,
        set_code=set_code,
        language=language,
        cards=candidates,
        cardmarket_expansion=cardmarket_expansion,
        cardmarket_version=cardmarket_version,
    )
    try:
        definition = parse_goal_manifest(manifest)
    except GoalManifestError as exc:
        raise click.ClickException(f"Generated an invalid candidate: {exc}") from exc

    output = output or (
        Path(current_app.instance_path) / "goal-candidates" / f"{slug}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as candidate_file:
            candidate_file.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    except FileExistsError as exc:
        raise click.ClickException(
            f"Candidate output already exists: {output}. Choose a new --output path."
        ) from exc
    click.echo(
        f"Wrote {len(definition.entries)} candidate entries to {output}. "
        "Review every printing and label before moving it into cardchart/goals."
    )

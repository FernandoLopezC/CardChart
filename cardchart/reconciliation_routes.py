import csv
import io
import json
import secrets
from datetime import date

import requests

from flask import (
    Blueprint, Response, abort, flash, redirect, render_template, request, session, url_for,
)

from .models import Card, ReconciliationBatch, db
from .reconciliation import (
    FIELDS, SOURCES, ReconciliationError, apply_review, column_suggestions,
    create_batch, map_batch, prepare_preview, update_matches,
)
from .scryfall_bulk import load_bulk_lookup

bp = Blueprint("reconciliation", __name__, url_prefix="/reconcile")


def csrf_token():
    if "reconciliation_csrf" not in session:
        session["reconciliation_csrf"] = secrets.token_urlsafe(32)
    return session["reconciliation_csrf"]


@bp.app_context_processor
def reconciliation_context():
    return {"csrf_token": csrf_token}


@bp.before_request
def protect_form():
    if request.method == "POST":
        submitted = request.form.get("csrf_token", "")
        expected = session.get("reconciliation_csrf", "")
        if not expected or not secrets.compare_digest(expected, submitted):
            abort(400, "This form expired. Reload the page and try again.")


def batch_or_404(batch_id):
    batch = db.session.get(ReconciliationBatch, batch_id)
    if batch is None:
        abort(404)
    return batch


@bp.route("/refresh-bulk", methods=["POST"])
def refresh_bulk():
    try:
        load_bulk_lookup(refresh=True)
    except (requests.RequestException, KeyError, OSError, ValueError) as exc:
        flash(f"Scryfall cache refresh failed: {exc}", "error")
    else:
        flash("Scryfall printing metadata is ready for matching.", "success")
    return redirect(url_for("reconciliation.index"))


@bp.route("", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            upload = request.files.get("csv_file")
            if not upload or not upload.filename:
                raise ReconciliationError("Choose a CSV export to reconcile.")
            batch = create_batch(upload, request.form)
        except ReconciliationError as exc:
            flash(str(exc), "error")
        else:
            return redirect(url_for("reconciliation.mapping", batch_id=batch.id))
    return render_template(
        "reconcile.html", batches=ReconciliationBatch.query.order_by(ReconciliationBatch.id.desc()).limit(50).all(),
        sources=SOURCES, today=date.today().isoformat(),
    )


@bp.route("/<int:batch_id>/map", methods=["GET", "POST"])
def mapping(batch_id):
    batch = batch_or_404(batch_id)
    if batch.state == "applied":
        return redirect(url_for("reconciliation.review", batch_id=batch.id))
    raw = json.loads(batch.raw_json)
    if request.method == "POST":
        try:
            map_batch(batch, request.form)
        except ReconciliationError as exc:
            flash(str(exc), "error")
        else:
            return redirect(url_for("reconciliation.review", batch_id=batch.id))
    suggestions = column_suggestions(raw["headers"])
    values = dict(suggestions, default_language="en")
    values.update(json.loads(batch.mapping_json))
    if request.method == "POST":
        values.update(request.form)
    return render_template(
        "reconcile_map.html", batch=batch, headers=raw["headers"], sample=raw["rows"][:5],
        fields=FIELDS, suggestions=suggestions, values=values,
    )


@bp.route("/<int:batch_id>/review", methods=["GET", "POST"])
def review(batch_id):
    batch = batch_or_404(batch_id)
    if batch.state == "mapping":
        return redirect(url_for("reconciliation.mapping", batch_id=batch.id))
    if request.method == "POST":
        try:
            if request.form.get("action") == "match":
                update_matches(batch, request.form)
            else:
                apply_review(batch, request.form)
        except ReconciliationError as exc:
            flash(str(exc), "error")
        else:
            flash("Printing matches updated; review the quantities before applying." if request.form.get("action") == "match" else "Selected rows recorded. Your inventory and linked goal quantities are up to date.", "success")
        return redirect(url_for("reconciliation.review", batch_id=batch.id))
    rows, inventory = [], []
    if batch.state == "review":
        try:
            rows, inventory = prepare_preview(batch)
        except (ReconciliationError, OSError, ValueError) as exc:
            db.session.rollback()
            flash(f"Cannot build this review: {exc}. Check the local bulk cache or remap the file.", "error")
            return redirect(url_for("reconciliation.mapping", batch_id=batch.id))
    return render_template(
        "reconcile_review.html", batch=batch, rows=rows, inventory=inventory,
        preview_token=batch.preview_token, results=json.loads(batch.results_json),
    )


@bp.route("/inventory.csv")
def export_inventory():
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Card Scryfall ID", "Name", "Set Code", "Set Name", "Collector Number", "Rarity", "Finish", "Finish Display", "Quantity"])
    for card in Card.query.filter(Card.quantity > 0).order_by(Card.name, Card.id).all():
        cells = [card.scryfall_id, card.name, card.set_code, card.set_name, card.collector_number, card.rarity, card.finish, card.finish_display, card.quantity]
        writer.writerow([f"'{value}" if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value for value in cells])
    return Response(output.getvalue(), content_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="cardchart-inventory.csv"'})

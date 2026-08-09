"""Family Quest Center Pack Store and parent pack-management routes."""

from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for

from services.content_packs import (
    archive_pack,
    get_pack_detail,
    get_pack_store_context,
    install_pack,
    update_pack_cosmetics,
    restore_pack,
)

content_packs_blueprint = Blueprint("content_packs", __name__, url_prefix="/parent/content-packs")


@content_packs_blueprint.route("/assets/<pack_key>/<path:filename>")
def asset(pack_key, filename):
    """Serve image assets bundled with a content pack."""
    pack_root = Path(current_app.root_path) / "content" / "packs" / pack_key
    if not (pack_root / "pack.json").is_file():
        abort(404)
    return send_from_directory(pack_root, filename)


@content_packs_blueprint.route("/")
def manager():
    """Legacy entry point; send parents to the Pack Store."""
    return redirect(url_for("content_packs.store"))


@content_packs_blueprint.route("/store")
def store():
    """Display the parent Pack Store browse page."""
    selected_filter = request.args.get("filter", "all").strip().lower()
    return render_template(
        "parent/content_packs/store.html",
        **get_pack_store_context(selected_filter=selected_filter),
    )


@content_packs_blueprint.route("/<pack_key>")
def detail(pack_key):
    """Display parent-facing Pack Store details."""
    try:
        pack = get_pack_detail(pack_key)
    except (FileNotFoundError, ValueError):
        flash("Content Pack not found.", "error")
        return redirect(url_for("content_packs.store"))
    return render_template("parent/content_packs/detail.html", pack=pack, store_child=None)


@content_packs_blueprint.route("/<pack_key>/install", methods=["POST"])
def install(pack_key):
    """Install one free pack directly when requested by a parent."""
    try:
        pack = get_pack_detail(pack_key)
        if pack.get("price_type", "free") != "free":
            raise ValueError("Paid Content Packs are not enabled yet.")
        counts = install_pack(pack_key)
    except (ValueError, FileNotFoundError) as exc:
        flash(str(exc), "error")
    else:
        flash(
            f"{pack['name']} installed for your family: {counts['quests']} quests, "
            f"{counts['adventures']} adventures, {counts['challenges']} challenges, "
            f"{counts['rewards']} rewards, {counts['books']} Quest Books, and {counts['avatars'] + counts['frames'] + counts['themes']} cosmetics.",
            "success",
        )
    return redirect(url_for("content_packs.store", filter="installed"))


@content_packs_blueprint.route("/<pack_key>/update", methods=["POST"])
def update(pack_key):
    """Synchronize the current manifest cosmetics for an installed pack."""
    try:
        pack = get_pack_detail(pack_key)
        counts = update_pack_cosmetics(pack_key)
    except (ValueError, FileNotFoundError) as exc:
        flash(str(exc), "error")
    else:
        flash(
            f"{pack['name']} updated: {counts['reward_categories']} reward categories added, "
            f"{counts['challenges_removed']} retired challenges removed, "
            f"{counts['avatars']} avatars, {counts['frames']} frames, "
            f"and {counts['themes']} themes synchronized.",
            "success",
        )
    return redirect(url_for("content_packs.store", filter="installed"))


@content_packs_blueprint.route("/<pack_key>/archive", methods=["POST"])
def archive(pack_key):
    """Archive an installed expansion pack."""
    try:
        archive_pack(pack_key)
    except (ValueError, FileNotFoundError) as exc:
        flash(str(exc), "error")
    else:
        flash("Content Pack archived. Completed history and individually archived items were preserved.", "success")
    return redirect(url_for("content_packs.store", filter="installed"))


@content_packs_blueprint.route("/<pack_key>/restore", methods=["POST"])
def restore(pack_key):
    """Restore a previously archived family pack."""
    try:
        restore_pack(pack_key)
    except (ValueError, FileNotFoundError) as exc:
        flash(str(exc), "error")
    else:
        flash("Content Pack restored for your family.", "success")
    return redirect(url_for("content_packs.store", filter="installed"))

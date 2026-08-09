"""Public and signed-in family home routes for Family Quest Center."""
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models.users import get_children
from models.cosmetics import get_character_profile
from services.content_packs import get_pack_detail, get_pack_store_context, request_pack
from services.quest_books import list_available_books
from services.account_auth import account_required


home_blueprint = Blueprint("home", __name__)


@home_blueprint.route("/")
def index():
    """Render the public landing page for every visitor."""
    return render_template("home.html")


@home_blueprint.route("/register")
def register():
    """Begin the public billing and family-registration workflow."""
    return redirect(url_for("account.register"))


@home_blueprint.route("/family/pack-store")
@account_required
def family_pack_store():
    """Display the shared family Pack Store in browse/request mode."""
    selected_filter = request.args.get("filter", "all").strip().lower()
    return render_template(
        "parent/content_packs/store.html",
        request_mode=True,
        **get_pack_store_context(selected_filter=selected_filter),
    )


@home_blueprint.route("/family/pack-store/<pack_key>")
@account_required
def family_pack_store_detail(pack_key: str):
    """Display one shared family Pack Store detail page."""
    try:
        pack = get_pack_detail(pack_key)
    except (FileNotFoundError, ValueError):
        flash("Content Pack not found.", "error")
        return redirect(url_for("home.family_pack_store"))
    return render_template(
        "parent/content_packs/detail.html",
        pack=pack,
        store_child=None,
        request_mode=True,
    )


@home_blueprint.post("/family/pack-store/<pack_key>/request")
@account_required
def family_pack_store_request(pack_key: str):
    """Create one family-level Pack Store request for parent approval."""
    try:
        result = request_pack(pack_key)
    except (ValueError, FileNotFoundError) as exc:
        flash(str(exc), "warning")
    else:
        flash(
            f"Request sent! A parent can review {result['pack']['name']} in the Approval Center.",
            "success",
        )
    return redirect(url_for("home.family_pack_store_detail", pack_key=pack_key))


@home_blueprint.route("/privacy")
def privacy():
    """Display the Family Quest Center privacy page."""
    return render_template("public/privacy.html")


@home_blueprint.route("/terms")
def terms():
    """Display the Family Quest Center terms page."""
    return render_template("public/terms.html")


@home_blueprint.route("/contact")
def contact():
    """Display Family Quest Center contact information."""
    return render_template("public/contact.html")


@home_blueprint.route("/family/quest-books")
@account_required
def family_quest_books():
    """Open the family Quest Books library without a second approval step."""
    children = []
    for child in get_children():
        if not child["active"]:
            continue
        child_data = dict(child)
        profile = get_character_profile(child)
        child_data["avatar_icon"] = (profile.get("avatar") or {}).get("icon") or child["initial"]
        child_data["avatar_image"] = (profile.get("avatar") or {}).get("image")
        children.append(child_data)

    active_child = None
    active_child_id = session.get("active_child_id")
    if active_child_id is not None:
        active_child = next((child for child in children if int(child["id"]) == int(active_child_id)), None)

    return render_template(
        "quest_books/library.html",
        books=list_available_books(active_child["id"] if active_child else None),
        children=children,
        child=active_child,
    )


@home_blueprint.route("/family")
@account_required
def family_dashboard():
    """Display the child profile selector for the signed-in family."""
    children = []
    for child in get_children():
        if not child["active"]:
            continue
        child_data = dict(child)
        profile = get_character_profile(child)
        child_data["avatar_icon"] = (profile.get("avatar") or {}).get("icon") or child["initial"]
        child_data["avatar_image"] = (profile.get("avatar") or {}).get("image")
        children.append(child_data)
    return render_template("family_dashboard.html", children=children)

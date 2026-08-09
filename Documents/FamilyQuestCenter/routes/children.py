"""Family Quest Center developer documentation.

File: routes/children.py
Purpose: Defines Flask routes and request-handling workflows for children features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from models.users import (
    create_child,
    get_child,
    get_child_details,
    get_children,
    set_child_active,
    update_child,
)

from models.administration import log_audit


children_blueprint = Blueprint(
    "children",
    __name__,
    url_prefix="/parent/children",
)


@children_blueprint.route("/")
def list_children():
    """Display active child profiles."""
    children = [child for child in get_children() if child["active"]]
    search = request.args.get("q", "").strip().lower()
    if search:
        children = [child for child in children if search in child["name"].lower()]
    return render_template(
        "parent/children/list.html",
        children=children,
        search_query=request.args.get("q", ""),
    )


@children_blueprint.route(
    "/add",
    methods=["GET", "POST"],
)
def add_child():
    """Create a new child profile."""

    if request.method == "POST":
        name = request.form.get(
            "name",
            "",
        ).strip()

        initial = request.form.get(
            "initial",
            "",
        ).strip().upper()

        if not name:
            flash(
                "Please enter a name.",
                "error",
            )

            return render_template(
                "parent/children/add.html",
            )

        if not initial:
            initial = name[0].upper()

        initial = initial[0]

        child_id = create_child(
            name=name,
            initial=initial,
        )
        log_audit(
            "child_created",
            "child",
            child_id,
            details=name,
        )

        flash(
            "Child added successfully.",
            "success",
        )

        return redirect(
            url_for("children.list_children")
        )

    return render_template(
        "parent/children/add.html",
    )


@children_blueprint.route("/<int:child_id>")
def view_child(child_id: int):
    """Display a child profile."""

    details = get_child_details(child_id)

    if details is None:
        abort(404)

    return render_template(
        "parent/children/view.html",
        **details,
    )


@children_blueprint.route(
    "/<int:child_id>/edit",
    methods=["GET", "POST"],
)
def edit_child(child_id: int):
    """Edit a child profile."""

    child = get_child(child_id)

    if child is None:
        abort(404)

    if request.method == "POST":
        name = request.form.get(
            "name",
            "",
        ).strip()

        initial = request.form.get(
            "initial",
            "",
        ).strip().upper()

        if not name:
            flash(
                "Please enter the child's name.",
                "error",
            )

            return render_template(
                "parent/children/edit.html",
                child=child,
            )

        if not initial:
            initial = name[0].upper()

        initial = initial[0]

        update_child(
            child_id=child_id,
            name=name,
            initial=initial,
        )

        flash(
            "Child profile updated successfully.",
            "success",
        )

        return redirect(
            url_for(
                "children.view_child",
                child_id=child_id,
            )
        )

    return render_template(
        "parent/children/edit.html",
        child=child,
    )


@children_blueprint.route(
    "/<int:child_id>/toggle",
    methods=["POST"],
)
def toggle_child(child_id: int):
    """Archive or restore a child profile."""

    child = get_child(child_id)

    if child is None:
        abort(404)

    new_status = not bool(child["active"])

    set_child_active(
        child_id=child_id,
        active=new_status,
    )
    log_audit(
        "child_restored" if new_status else "child_archived",
        "child",
        child_id,
        details=child["name"],
    )

    if new_status:
        flash(
            "Child profile restored.",
            "success",
        )
    else:
        flash(
            "Child profile archived.",
            "success",
        )

    if new_status:
        return redirect(
            url_for(
                "children.edit_child",
                child_id=child_id,
            )
        )

    # FC-0031: after archiving, return to the active Family Members list.
    return redirect(url_for("children.list_children"))

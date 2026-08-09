"""Family Quest Center developer documentation.

File: routes/child.py
Purpose: Defines Flask routes and request-handling workflows for child features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from models.achievements import (
    get_achievement_summary, get_child_achievements,
    mark_achievement_notifications_seen, pop_pending_achievement_notifications,
)
from services.mission_service import (
    complete_mission,
    generate_missions_for_date,
    get_mission,
    list_child_missions,
    submit_mission_for_approval,
)
from services.content_packs import get_pack_detail, get_pack_store_context, request_pack
from services.adventure_service import (
    can_complete_journey,
    complete_journey,
    get_journey_assignment,
    submit_journey_for_approval,
)
from models.cosmetics import (
    get_character_profile,
    get_cosmetic_options,
    save_character_choices,
)
from models.progression import build_progression
from models.family_progression import (
    get_activity_heatmap, get_child_statistics, get_child_timeline,
    group_timeline_by_day, refresh_streak,
)
from models.users import get_user_by_id
from models.family_challenges import list_challenges
from models.journeys import (
    current_child_journeys, complete_journey_instance,
    list_child_adventure_celebrations, list_child_completed_journeys_today,
)


child_blueprint = Blueprint("child", __name__, url_prefix="/child")


def _flash_achievement_unlocks(child_id: int, achievements: list[dict]) -> None:
    """Handle the flash achievement unlocks workflow."""
    for achievement in achievements:
        reward_parts = []
        if achievement["xp_reward"]:
            reward_parts.append(f"+{achievement['xp_reward']} XP")
        if achievement["star_reward"]:
            reward_parts.append(f"+{achievement['star_reward']} stars")
        reward_text = f" Reward: {', '.join(reward_parts)}." if reward_parts else ""
        flash(
            f"{achievement['icon']} Achievement unlocked: "
            f"{achievement['name']}!{reward_text}",
            "achievement",
        )
    mark_achievement_notifications_seen(
        child_id, [int(achievement["id"]) for achievement in achievements]
    )


@child_blueprint.route("/<int:user_id>")
def dashboard(user_id: int):
    """Handle the dashboard workflow."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)

    from services.onboarding import child_training_complete
    if request.args.get("trained") != "1" and not child_training_complete(user_id):
        return redirect(url_for("onboarding.explorer_training", user_id=user_id))

    _flash_achievement_unlocks(child["id"], pop_pending_achievement_notifications(child["id"]))

    generate_missions_for_date(date.today())
    assignments = list_child_missions(child["id"], date.today().isoformat())
    journeys = current_child_journeys(child["id"])
    streaks = refresh_streak(child["id"])
    child = get_user_by_id(user_id)
    progression = build_progression(child["total_xp"])
    achievement_summary = get_achievement_summary(child["id"])
    character = get_character_profile(child)
    active_challenge = next(
        (challenge for challenge in list_challenges() if challenge.get("display_status") == "active"),
        None,
    )

    return render_template(
        "child/dashboard.html",
        child=child,
        assignments=assignments,
        progression=progression,
        achievement_summary=achievement_summary,
        character=character,
        streaks=streaks,
        journeys=journeys,
        completed_journeys=list_child_completed_journeys_today(child["id"]),
        adventure_celebrations=list_child_adventure_celebrations(child["id"]),
        active_challenge=active_challenge,
    )


@child_blueprint.route("/<int:user_id>/character", methods=["GET", "POST"])
def character(user_id: int):
    """Handle the character workflow."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)

    if request.method == "POST":
        success, message = save_character_choices(
            child_id=child["id"],
            avatar_key=request.form.get("avatar_key", ""),
            frame_key=request.form.get("frame_key", ""),
            theme_key=request.form.get("theme_key", ""),
        )
        flash(message, "success" if success else "error")
        if success:
            return redirect(url_for("child.character", user_id=child["id"]))

    child = get_user_by_id(user_id)
    return render_template(
        "child/character.html",
        child=child,
        progression=build_progression(child["total_xp"]),
        character=get_character_profile(child),
        cosmetics=get_cosmetic_options(child["id"]),
    )


@child_blueprint.route("/<int:user_id>/achievements")
def trophy_room(user_id: int):
    """Handle the trophy room workflow."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    achievements = get_child_achievements(child["id"])
    return render_template(
        "child/trophy_room.html",
        child=child,
        achievements=achievements,
        earned_count=sum(1 for achievement in achievements if achievement["earned"]),
        total_count=len(achievements),
    )


@child_blueprint.route("/complete/<int:assignment_id>", methods=["POST"])
def complete(assignment_id: int):
    """Complete either a Responsibility Mission or today's Journey.

    The shared URL is retained for Version 1 template compatibility, while the
    workflow is dispatched to separate service boundaries.
    """

    assignment = get_mission(assignment_id)
    activity_kind = "mission"

    if assignment is None:
        assignment = get_journey_assignment(assignment_id)
        activity_kind = "journey"

    if assignment is None:
        abort(404)

    if assignment["status"] != "assigned":
        flash("This activity has already been completed or submitted.", "warning")
        return redirect(url_for("child.dashboard", user_id=assignment["child_id"]))

    if activity_kind == "journey":
        allowed, message = can_complete_journey(assignment_id)
        if not allowed:
            flash(message, "warning")
            return redirect(url_for("child.dashboard", user_id=assignment["child_id"]))

        if assignment["approval_required"]:
            completed = submit_journey_for_approval(assignment_id)
            flash(
                "Chapter submitted for parent approval." if completed
                else "This journey could not be submitted again.",
                "success" if completed else "warning",
            )
        else:
            result = complete_journey(assignment_id)
            if result:
                flash("Chapter completed!", "success")
                _flash_achievement_unlocks(assignment["child_id"], result["achievements"])
                if result.get("chain_completed"):
                    chain = result["chain_completed"]
                    flash(
                        f"🗺️ Adventure completed: {chain['name']}! "
                        f"Bonus: +{chain['bonus_xp']} XP and +{chain['bonus_stars']} stars.",
                        "achievement",
                    )
            else:
                flash("This journey could not be rewarded again.", "warning")
    else:
        if assignment["approval_required"]:
            completed = submit_mission_for_approval(assignment_id)
            flash(
                "Quest submitted for parent approval." if completed
                else "This quest could not be submitted again.",
                "success" if completed else "warning",
            )
        else:
            result = complete_mission(assignment_id)
            if result:
                flash(
                    f"Quest completed! You earned {assignment['stars']} stars "
                    f"and {assignment['xp_reward']} XP!",
                    "success",
                )
                _flash_achievement_unlocks(assignment["child_id"], result["achievements"])
            else:
                flash("This quest could not be rewarded again.", "warning")

    return redirect(
        url_for("child.dashboard", user_id=assignment["child_id"])
        + f"#quest-card-{assignment_id}"
    )


@child_blueprint.route("/<int:user_id>/journeys/<int:journey_instance_id>/complete", methods=["POST"])
def complete_today_journey(user_id: int, journey_instance_id: int):
    """Handle the complete today journey workflow."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    result = complete_journey_instance(journey_instance_id)
    if result is None or result["child_id"] != user_id:
        flash("This Chapter could not be completed.", "warning")
    elif result.get("adventure_ready"):
        flash(f"🎉 Final Chapter complete! {result['adventure_name']} is ready for your Quest Master to celebrate.", "achievement")
    else:
        flash(f"🎉 Chapter complete! Chapter {result['next_step']} is now unlocked.", "success")
    return_to = request.args.get("next", "dashboard").strip().lower()
    if return_to == "adventures":
        return redirect(url_for("child_adventures.child_chains", user_id=user_id))
    if return_to == "dashboard_adventures":
        return redirect(
            url_for("child.dashboard", user_id=user_id, view="journey")
            + f"#adventure-card-{journey_instance_id}"
        )
    return redirect(url_for("child.dashboard", user_id=user_id))


@child_blueprint.route("/<int:user_id>/progress")
def progress(user_id: int):
    """Handle the progress workflow."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    refresh_streak(child["id"])
    child = get_user_by_id(user_id)
    return render_template(
        "child/progress.html", child=child,
        progression=build_progression(child["total_xp"]),
        character=get_character_profile(child),
        statistics=get_child_statistics(child["id"]),
        heatmap=get_activity_heatmap(child["id"]),
    )


@child_blueprint.route("/<int:user_id>/timeline")
def timeline(user_id: int):
    """Handle the timeline workflow."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    events = get_child_timeline(child["id"])
    return render_template(
        "child/timeline.html", child=child,
        character=get_character_profile(child),
        timeline_groups=group_timeline_by_day(events),
    )

@child_blueprint.route("/<int:user_id>/pack-store")
def pack_store(user_id: int):
    """Let a child browse family Content Packs and request one from a parent."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    selected_filter = request.args.get("filter", "all").strip().lower()
    try:
        context = get_pack_store_context(child_id=user_id, selected_filter=selected_filter)
    except ValueError:
        abort(404)
    return render_template("parent/content_packs/store.html", child=child, **context)


@child_blueprint.route("/<int:user_id>/pack-store/<pack_key>")
def pack_store_detail(user_id: int, pack_key: str):
    """Display one pack to a child without exposing parent install controls."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    try:
        pack = get_pack_detail(pack_key, child_id=user_id)
    except (FileNotFoundError, ValueError):
        flash("Content Pack not found.", "error")
        return redirect(url_for("child.pack_store", user_id=user_id))
    return render_template("parent/content_packs/detail.html", child=child, pack=pack, store_child=dict(child))


@child_blueprint.post("/<int:user_id>/pack-store/<pack_key>/request")
def request_content_pack(user_id: int, pack_key: str):
    """Send one family-level Pack Store request to the parent's Approval Center."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    try:
        result = request_pack(pack_key)
    except (ValueError, FileNotFoundError) as exc:
        flash(str(exc), "warning")
    else:
        flash(f"Request sent! Your parent can review {result['pack']['name']} in the Approval Center.", "success")
    return redirect(url_for("child.pack_store_detail", user_id=user_id, pack_key=pack_key))
@child_blueprint.route("/<int:user_id>/quest-books")
def quest_books(user_id: int):
    """Display installed-pack Quest Books for one explorer."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    from services.quest_books import list_available_books
    return render_template(
        "quest_books/library.html",
        child=child,
        character=get_character_profile(child),
        children=[],
        books=list_available_books(child["id"]),
    )


@child_blueprint.route("/<int:user_id>/quest-books/<book_key>")
def read_quest_book(user_id: int, book_key: str):
    """Start or continue one branching Quest Book."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    from services.quest_books import get_reader_context
    try:
        context = get_reader_context(child["id"], book_key)
    except FileNotFoundError:
        abort(404)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("child.quest_books", user_id=child["id"]))
    return render_template("quest_books/reader.html", **context)


@child_blueprint.post("/<int:user_id>/quest-books/<book_key>/choose")
def choose_quest_book_path(user_id: int, book_key: str):
    """Save one branching story choice for the active child."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    from services.quest_books import choose_path
    try:
        result = choose_path(child["id"], book_key, request.form.get("next_node", ""))
    except FileNotFoundError:
        abort(404)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("child.read_quest_book", user_id=child["id"], book_key=book_key) + "#quest-book-reader")
    if result["completed"]:
        if result["xp_awarded"]:
            flash(f"Quest Book complete! +{result['xp_awarded']} XP", "achievement")
        else:
            flash("Quest Book complete! Great adventure.", "success")
    return redirect(url_for("child.read_quest_book", user_id=child["id"], book_key=book_key) + "#quest-book-reader")


@child_blueprint.post("/<int:user_id>/quest-books/<book_key>/restart")
def restart_quest_book(user_id: int, book_key: str):
    """Restart a completed Quest Book without repeat XP."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    from services.quest_books import restart_book
    try:
        restart_book(child["id"], book_key)
    except FileNotFoundError:
        abort(404)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("child.quest_books", user_id=child["id"]) + "#quest-book-reader")
    return redirect(url_for("child.read_quest_book", user_id=child["id"], book_key=book_key) + "#quest-book-reader")


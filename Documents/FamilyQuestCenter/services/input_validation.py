"""Central request validation for common Family Quest Center form fields."""
from __future__ import annotations

from flask import abort, current_app, request

# Conservative server-side limits. Feature routes may impose stricter rules.
FIELD_MAX_LENGTHS = {
    "name": 100,
    "family_name": 100,
    "application_name": 100,
    "display_name": 100,
    "title": 120,
    "description": 2000,
    "notes": 2000,
    "reward_text": 500,
    "email": 254,
    "initial": 4,
    "icon": 16,
    "category": 60,
    "timezone": 64,
    "country": 80,
    "date_format": 20,
    "notification_key": 120,
    "return_to": 120,
    "next": 500,
    "chapter_name": 120,
    "chapter_description": 1000,
}

# Protect the parser and application from excessive repeated list fields.
MAX_VALUES_PER_FIELD = 100
MAX_FORM_FIELDS = 250


def validate_common_form_input() -> None:
    """Reject oversized form submissions before feature logic runs."""
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return

    if len(request.form) > MAX_FORM_FIELDS:
        current_app.logger.warning("Rejected form with too many fields: %s", request.path)
        abort(400, description="The submitted form contained too many fields.")

    for key in request.form.keys():
        values = request.form.getlist(key)
        if len(values) > MAX_VALUES_PER_FIELD:
            current_app.logger.warning("Rejected form with too many values for %s: %s", key, request.path)
            abort(400, description="The submitted form contained too many repeated values.")

        limit = FIELD_MAX_LENGTHS.get(key)
        if limit is None:
            continue
        for value in values:
            if len(value) > limit:
                current_app.logger.warning(
                    "Rejected oversized field %s (%s chars) on %s", key, len(value), request.path
                )
                abort(400, description=f"The {key.replace('_', ' ')} value was too long.")

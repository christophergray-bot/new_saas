"""Family Quest Center developer documentation.

File: routes/journeys.py
Purpose: Defines Flask routes and request-handling workflows for journeys features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from flask import Blueprint,flash,redirect,url_for
journeys_blueprint=Blueprint('journeys',__name__,url_prefix='/parent/journeys')

@journeys_blueprint.route('/')
def library():
    """Handle the library workflow."""
    flash('Chapters are now created inside each Adventure.','info')
    return redirect(url_for('parent_adventures.chains'))

@journeys_blueprint.route('/new')
def new():
    """Handle the new workflow."""
    return redirect(url_for('parent_adventures.new_chain'))

@journeys_blueprint.route('/<int:journey_id>/edit')
def edit(journey_id):
    """Handle the edit workflow."""
    return redirect(url_for('parent_adventures.chains'))

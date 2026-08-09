"""Automated regression/validation coverage.

File: tests/test_child_dashboard_adventure_completion_regression.py
Reviewed for v1.7.0-rc1 cleanup.
"""
from pathlib import Path


def test_pending_adventure_card_uses_adventure_id_not_finished_journey_variable():
    template = Path("templates/child/dashboard.html").read_text(encoding="utf-8")
    pending_loop = template.split("{% for adventure in pending_adventures %}", 1)[1].split("{% endfor %}", 1)[0]
    assert 'id="adventure-card-{{ adventure.id }}"' in pending_loop
    assert 'id="adventure-card-{{ journey.id }}"' not in pending_loop

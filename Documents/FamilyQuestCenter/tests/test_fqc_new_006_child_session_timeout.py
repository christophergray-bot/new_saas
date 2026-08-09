"""Automated regression/validation coverage.

File: tests/test_fqc_new_006_child_session_timeout.py
Reviewed for v1.7.0-rc1 cleanup.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_child_session_timeout_default_and_settings_ui():
    settings = (ROOT / "models/settings.py").read_text(encoding="utf-8")
    template = (ROOT / "templates/parent_management/family_settings.html").read_text(encoding="utf-8")
    route = (ROOT / "routes/parent_management.py").read_text(encoding="utf-8")
    assert '"child_session_timeout_seconds": "43200"' in settings
    assert 'name="child_session_timeout_seconds"' in template
    assert '43,200 seconds (12 hours)' in template
    assert 'request.form.get("child_session_timeout_seconds", "43200")' in route

def test_parent_and_child_use_separate_inactivity_timers():
    auth = (ROOT / "routes/auth.py").read_text(encoding="utf-8")
    assert 'get_int_setting("session_timeout_seconds", 600)' in auth
    assert 'get_int_setting("child_session_timeout_seconds", 43200)' in auth
    assert 'session["parent_last_activity_at"]' in auth
    assert 'session["child_last_activity_at"]' in auth
    assert 'session.pop("parent_authenticated", None)' in auth
    assert 'Explorer session ended after inactivity.' in auth

def test_child_mode_does_not_preserve_parent_authorization():
    auth = (ROOT / "routes/auth.py").read_text(encoding="utf-8")
    child_block = auth[auth.index("# FC-0021 / ADJ-0015 / FQC-NEW-006:"):auth.index("path_is_protected = any(")]
    assert 'session.pop("parent_authenticated", None)' in child_block
    assert 'session.pop("parent_last_activity_at", None)' in child_block

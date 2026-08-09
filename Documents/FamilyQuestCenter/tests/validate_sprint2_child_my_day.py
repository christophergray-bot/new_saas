"""Automated regression/validation coverage.

File: tests/validate_sprint2_child_my_day.py
Reviewed for v1.7.0-rc1 cleanup.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
template = (root / 'templates/child/dashboard.html').read_text()
style = (root / 'static/style.css').read_text()
route = (root / 'routes/child.py').read_text()
journeys = (root / 'models/journeys.py').read_text()

checks = {
    'Mission To Do toggle': 'data-status-tab="missions-todo"' in template,
    'Mission Done toggle': 'data-status-tab="missions-done"' in template,
    'Adventure To Do toggle': 'data-status-tab="adventures-todo"' in template,
    'Adventure Done toggle': 'data-status-tab="adventures-done"' in template,
    'To Do defaults': template.count('child-status-tab is-active') >= 2,
    'Scrollable lists': 'child-scroll-list' in template and 'overflow-y: auto' in style,
    'Fixed-height lists': 'max-height:' in style,
    'Completed chapters query': 'def list_child_completed_journeys_today' in journeys,
    'Completed chapters route binding': 'completed_journeys=list_child_completed_journeys_today' in route,
    'Nested toggle script': "querySelectorAll('.child-today-view')" in template,
}

for label, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'}: {label}")

if not all(checks.values()):
    raise SystemExit(1)

logic_checks = {
    'Pending missions remain To Do': "rejectattr('status', 'equalto', 'approved')" in template,
    'Only approved missions are Done': "selectattr('status', 'equalto', 'approved')" in template,
    'Pending Adventures remain To Do': "pending_adventures" in template and 'Waiting for Approval' in template,
    'Only approved Adventures are Done': "approved_adventures" in template,
}
for name, passed in logic_checks.items():
    print(('PASS' if passed else 'FAIL') + ': ' + name)
    if not passed:
        raise SystemExit(1)

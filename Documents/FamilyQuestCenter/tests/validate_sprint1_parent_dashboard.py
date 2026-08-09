"""Dependency-light validation for Sprint 1 Parent Dashboard changes."""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _activity_query() -> str:
    source = (ROOT / "models" / "dashboard.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "get_recent_activity"
    )
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and "SELECT activity_type" in node.args[0].value
        ):
            return node.args[0].value
    raise AssertionError("Recent activity query was not found.")


def main() -> None:
    dashboard_template = (ROOT / "templates" / "parent" / "dashboard.html").read_text(encoding="utf-8")
    family_template = (ROOT / "templates" / "family_dashboard.html").read_text(encoding="utf-8")
    stylesheet = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    dashboard_model = (ROOT / "models" / "dashboard.py").read_text(encoding="utf-8")
    parent_route = (ROOT / "routes" / "parent.py").read_text(encoding="utf-8")

    assert dashboard_template.count("<h2>Pending Approvals</h2>") == 1
    assert "dashboard-action-required-grid" in dashboard_template
    assert "Reward Request" in dashboard_template
    assert "dashboard-recent-activity-section .dashboard-activity-list" in stylesheet
    assert "overflow-y: auto" in stylesheet
    assert "get_recent_activity(limit=50)" in parent_route
    assert "+ len(pending_reward_requests)" in parent_route
    assert "adventure_instances_v2" in dashboard_model
    assert "current_adventures_row" in dashboard_model
    assert "child.avatar_icon or child.initial" in family_template

    database_path = ROOT / "tests" / "fixtures" / "baseline.db"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    family = connection.execute("SELECT id FROM families ORDER BY id LIMIT 1").fetchone()
    if family is not None:
        sql = _activity_query()
        placeholder_count = sql.count("?")
        params = [int(family["id"])] * (placeholder_count - 1) + [50]
        connection.execute(sql, params).fetchall()
    connection.close()
    print("Sprint 1 Parent Dashboard validation passed.")


if __name__ == "__main__":
    main()

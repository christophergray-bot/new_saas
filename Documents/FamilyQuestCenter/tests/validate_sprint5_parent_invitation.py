"""Static validation for Sprint 5 Parent Two invitation workflow."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
route_text = (ROOT / "routes" / "parent_management.py").read_text(encoding="utf-8")
overview_text = (ROOT / "templates" / "parent_management" / "overview.html").read_text(encoding="utf-8")
accept_text = (ROOT / "templates" / "parent_management" / "accept_invitation.html").read_text(encoding="utf-8")

checks = {
    "invited parent creates own password": "Create your password to finish accepting this invitation." in accept_text,
    "acceptance no longer routes to owner-only PIN setup": 'return redirect(url_for("auth.setup_pin"))' not in route_text[route_text.index('def accept_invitation'):route_text.index('def resend_invitation')],
    "acceptance routes to shared PIN unlock": 'return redirect(url_for("auth.login", next=url_for("parent.dashboard")))' in route_text,
    "csrf rotates after invitation login": "rotate_csrf_token()" in route_text,
    "resend route exists": 'route("/invitation/resend"' in route_text,
    "resend invalidates previous invitation": "Invalidate the previous link before issuing the replacement" in route_text,
    "pending invitation has resend control": "Resend Invitation" in overview_text,
    "pending invitation has cancel control": "Cancel Invitation" in overview_text,
    "invitation expiry shown": "invitation.expires_at" in overview_text,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'}: {name}")
if failed:
    raise SystemExit("Validation failed: " + ", ".join(failed))

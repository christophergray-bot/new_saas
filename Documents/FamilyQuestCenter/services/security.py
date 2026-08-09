"""Application security helpers for CSRF protection, throttling, and headers."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from flask import abort, current_app, request, session

from database import get_db

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def get_csrf_token() -> str:
    """Return the current session CSRF token, creating one when necessary."""
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def rotate_csrf_token() -> str:
    """Replace the session CSRF token after a security-boundary change."""
    session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def validate_csrf_request() -> None:
    """Reject state-changing requests without the matching session token."""
    if request.method in SAFE_METHODS:
        return
    # Stripe authenticates its webhook with a signed payload rather than a browser CSRF token.
    if request.endpoint == "billing.webhook":
        return

    expected = session.get("csrf_token")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not expected or not supplied or not hmac.compare_digest(str(expected), str(supplied)):
        current_app.logger.warning(
            "Rejected request with missing or invalid CSRF token: %s %s",
            request.method,
            request.path,
        )
        abort(400, description="The security token was missing or expired. Refresh the page and try again.")


def ensure_rate_limit_table() -> None:
    """Create the persistent rate-limit table used across app workers."""
    db = get_db()
    db.execute(
        """CREATE TABLE IF NOT EXISTS security_rate_limits (
            action TEXT NOT NULL,
            subject_hash TEXT NOT NULL,
            window_started_at TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            blocked_until TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(action, subject_hash)
        )"""
    )
    db.commit()


def _subject_hash(subject: str) -> str:
    return hashlib.sha256(subject.encode("utf-8", errors="ignore")).hexdigest()


def client_ip() -> str:
    """Return the client address after ProxyFix has normalized the request."""
    return request.remote_addr or "unknown"


def rate_limit_subject(*parts: object) -> str:
    """Build a non-secret rate-limit subject from normalized identifiers."""
    return "|".join(str(part).strip().lower() for part in parts if part is not None)


def rate_limit_is_blocked(action: str, subject: str) -> tuple[bool, int]:
    """Return whether an action is blocked and the remaining seconds."""
    ensure_rate_limit_table()
    now = datetime.now(timezone.utc)
    row = get_db().execute(
        "SELECT blocked_until FROM security_rate_limits WHERE action=? AND subject_hash=?",
        (action, _subject_hash(subject)),
    ).fetchone()
    if not row or not row["blocked_until"]:
        return False, 0
    try:
        blocked_until = datetime.fromisoformat(row["blocked_until"])
    except ValueError:
        return False, 0
    if blocked_until.tzinfo is None:
        blocked_until = blocked_until.replace(tzinfo=timezone.utc)
    remaining = int((blocked_until - now).total_seconds())
    return (remaining > 0, max(0, remaining))


def record_rate_limit_failure(
    action: str,
    subject: str,
    *,
    max_attempts: int,
    window_seconds: int,
    block_seconds: int,
) -> None:
    """Record a failed attempt and apply a temporary block at the threshold."""
    ensure_rate_limit_table()
    db = get_db()
    now = datetime.now(timezone.utc)
    key = _subject_hash(subject)
    row = db.execute(
        "SELECT window_started_at,attempt_count FROM security_rate_limits WHERE action=? AND subject_hash=?",
        (action, key),
    ).fetchone()

    attempts = 1
    window_start = now
    if row:
        try:
            existing_start = datetime.fromisoformat(row["window_started_at"])
            if existing_start.tzinfo is None:
                existing_start = existing_start.replace(tzinfo=timezone.utc)
        except ValueError:
            existing_start = now
        if now - existing_start <= timedelta(seconds=window_seconds):
            attempts = int(row["attempt_count"]) + 1
            window_start = existing_start

    blocked_until = None
    if attempts >= max_attempts:
        blocked_until = (now + timedelta(seconds=block_seconds)).isoformat(timespec="seconds")
        attempts = 0
        window_start = now

    db.execute(
        """INSERT INTO security_rate_limits(
               action,subject_hash,window_started_at,attempt_count,blocked_until,updated_at
           ) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(action,subject_hash) DO UPDATE SET
               window_started_at=excluded.window_started_at,
               attempt_count=excluded.attempt_count,
               blocked_until=excluded.blocked_until,
               updated_at=CURRENT_TIMESTAMP""",
        (action, key, window_start.isoformat(timespec="seconds"), attempts, blocked_until),
    )
    db.commit()


def clear_rate_limit(action: str, subject: str) -> None:
    """Clear failures after successful authentication."""
    ensure_rate_limit_table()
    db = get_db()
    db.execute(
        "DELETE FROM security_rate_limits WHERE action=? AND subject_hash=?",
        (action, _subject_hash(subject)),
    )
    db.commit()


def apply_security_headers(response):
    """Attach browser security headers without breaking the current inline UI."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self' https://checkout.stripe.com https://billing.stripe.com; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'",
    )
    if current_app.config.get("SESSION_COOKIE_SECURE"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

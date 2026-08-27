"""Periodic cleanup of rows nothing will ever read again.

None of this is load-bearing: `resolve_session` already refuses an expired
session and `consume_password_reset` already refuses a spent token, so the
application is correct whether or not this runs. It exists because both tables
are append-only in practice, and a table that only grows eventually becomes a
backup problem, an index problem, and then somebody's afternoon.

Run rarely. There is nothing time-critical here, and a DELETE over an
authentication table is not something to do every fifteen seconds.
"""

from __future__ import annotations

import logging

from app.services import auth_service

log = logging.getLogger(__name__)


def purge_stale_auth_rows() -> int:
    """Delete expired sessions and spent reset tokens. Returns the row count."""
    sessions = auth_service.purge_expired_sessions()
    resets = auth_service.purge_spent_password_resets()

    total = sessions + resets
    if total:
        log.info("housekeeping: removed %d expired sessions, %d spent resets", sessions, resets)
    return total

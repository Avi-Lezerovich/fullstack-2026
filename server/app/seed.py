"""One-shot database seeding: `python -m app.seed`.

Run as its own process, never from `create_app()`. The factory is deliberately
side-effect-free (see app/__init__.py), and seeding from it would put several
gunicorn workers in a race to insert the same rows.

**Idempotent by construction.** Every insert is keyed on a natural key that is
stable across runs - a user's email, a case's title - and re-running only
refreshes the descriptive columns. That is what lets compose run this as a
`restart: no` service on every `up` without accumulating duplicates, and what
makes it safe to point at an RDS instance that already holds real data.

Passwords: all seeded accounts share `seed_data.DEMO_PASSWORD`. The bcrypt hash
is computed **once** and reused, because hashing twenty-three times at twelve
rounds costs about seven seconds for no benefit - they are the same password.
"""

from __future__ import annotations

import logging

from .db import Db, wait_for_db
from .security import hash_password
from .services import cases_service
from . import seed_data

log = logging.getLogger("app.seed")


def _upsert_user(
    db: Db,
    *,
    email: str,
    name: str,
    bio: str | None,
    password_hash: str,
    is_admin: bool = False,
    is_bot: bool = False,
) -> int:
    """Insert or refresh one user, returning its id.

    `password_hash` is only written on insert: re-seeding must not reset the
    password of an account somebody has since changed.
    """
    db.execute(
        "INSERT INTO users (name, email, password_hash, bio, is_admin, is_bot, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, UTC_TIMESTAMP()) "
        "ON DUPLICATE KEY UPDATE name = VALUES(name), bio = VALUES(bio), "
        "                        is_admin = VALUES(is_admin), is_bot = VALUES(is_bot)",
        (name, email, password_hash, bio, int(is_admin), int(is_bot)),
    )
    return int(db.query_value("SELECT id FROM users WHERE email = %s", (email,)))


def _upsert_agent(db: Db, user_id: int, agent: dict) -> None:
    """Insert or refresh the `agents` row that turns a user into a bot.

    `last_social_action_at` is left alone on update - it is pacing state owned
    by the worker, and resetting it on every deploy would make the bots flood
    the feed the moment the stack comes back up.
    """
    db.execute(
        "INSERT INTO agents (user_id, role, moderator_kind, personality_name, "
        "                    personality_prompt, tone_tag, guilt_bias, tiebreak_lean, is_active) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1) "
        "ON DUPLICATE KEY UPDATE role = VALUES(role), "
        "                        moderator_kind = VALUES(moderator_kind), "
        "                        personality_name = VALUES(personality_name), "
        "                        personality_prompt = VALUES(personality_prompt), "
        "                        tone_tag = VALUES(tone_tag), "
        "                        guilt_bias = VALUES(guilt_bias), "
        "                        tiebreak_lean = VALUES(tiebreak_lean), "
        "                        is_active = 1",
        (
            user_id,
            agent["role"],
            agent.get("moderator_kind"),
            agent["personality_name"],
            agent["personality_prompt"],
            agent["tone_tag"],
            agent.get("guilt_bias", 0.50),
            agent.get("tiebreak_lean"),
        ),
    )


def seed_agents(db: Db, password_hash: str) -> int:
    """The nineteen court personalities: a user row plus an agents row each."""
    for agent in seed_data.all_agents():
        user_id = _upsert_user(
            db,
            email=agent["email"],
            name=agent["personality_name"],
            bio=agent.get("bio"),
            password_hash=password_hash,
            is_bot=True,
        )
        _upsert_agent(db, user_id, agent)
    return len(seed_data.all_agents())


def seed_humans(db: Db, password_hash: str) -> list[int]:
    """The admin plus the demo accounts. Returns their ids, admin first."""
    ids = [
        _upsert_user(
            db,
            email=seed_data.ADMIN["email"],
            name=seed_data.ADMIN["name"],
            bio=seed_data.ADMIN.get("bio"),
            password_hash=password_hash,
            is_admin=True,
        )
    ]
    for human in seed_data.DEMO_HUMANS:
        ids.append(
            _upsert_user(
                db,
                email=human["email"],
                name=human["name"],
                bio=human.get("bio"),
                password_hash=password_hash,
            )
        )
    return ids


def seed_demo_case(db: Db, author_id: int) -> bool:
    """File the opening lawsuit, so a fresh deployment has a non-empty feed.

    Keyed on the title, and created with `screen=False` so seeding never
    depends on the moderation brain (or, with a provider configured, on a
    network call to it).
    """
    case = seed_data.DEMO_CASE
    exists = db.query_value("SELECT id FROM cases WHERE title = %s LIMIT 1", (case["title"],))
    if exists:
        return False

    cases_service.create_case(
        author_id,
        case["title"],
        case["body"],
        case["defendant_text"],
        charges=case["charges"],
        moderation_status="published",
        screen=False,
        conn=db,
    )
    return True


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )

    # The seed service starts alongside a MySQL container that may still be
    # running its own entrypoint, so waiting is the normal path, not an error.
    db = wait_for_db()
    try:
        password_hash = hash_password(seed_data.DEMO_PASSWORD)

        agents = seed_agents(db, password_hash)
        humans = seed_humans(db, password_hash)
        db.commit()

        filed = seed_demo_case(db, humans[1])
        db.commit()

        log.info(
            "seeded %d agents, %d human accounts, demo case: %s",
            agents,
            len(humans),
            "created" if filed else "already present",
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()

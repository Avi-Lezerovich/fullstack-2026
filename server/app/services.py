"""Business logic — parameterized raw SQL queries that return the exact JSON
shapes the client expects (see client/src/types.ts).
"""
import secrets
import datetime

from .models import get_db
from .utils import hash_password, verify_password

# Posts always come back joined with their author's name.
POSTS_SELECT = (
    "SELECT p.*, u.name AS author_name "
    "FROM posts p JOIN users u ON u.id = p.author_id"
)


def _now_iso() -> str:
    dt = datetime.datetime.now(datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _public_user(row) -> dict:
    """User without the password hash."""
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "bio": row["bio"],
        "avatar_url": row["avatar_url"],
        "created_at": row["created_at"],
    }


def _charges_for(conn, post_id: int) -> list:
    rows = conn.execute(
        "SELECT charge FROM post_charges WHERE post_id = ? ORDER BY id", (post_id,)
    ).fetchall()
    return [r["charge"] for r in rows]


def _post_to_dict(conn, row) -> dict:
    charges = _charges_for(conn, row["id"])
    return {
        "id": row["id"],
        "title": row["title"],
        "body": row["body"],
        "defendant": row["defendant"],
        "image_url": row["image_url"],
        "charges": charges or None,  # null when there are none (matches old mock)
        "author_id": row["author_id"],
        "author_name": row["author_name"],
        "created_at": row["created_at"],
    }


# ------------------------------------------------------------------------ users

def create_user(name: str, email: str, password: str, conn=None) -> dict:
    """Create a user. Raises ValueError if the email is already taken."""
    own = conn is None
    conn = conn or get_db()
    try:
        taken = conn.execute(
            "SELECT 1 FROM users WHERE LOWER(email) = LOWER(?)", (email.strip(),)
        ).fetchone()
        if taken:
            raise ValueError("האימייל כבר רשום במערכת")
        cur = conn.execute(
            "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (name.strip(), email.strip(), hash_password(password), _now_iso()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _public_user(row)
    finally:
        if own:
            conn.close()


def authenticate(email: str, password: str, conn=None):
    """Return the public user on valid credentials, else None."""
    own = conn is None
    conn = conn or get_db()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email.strip(),)
        ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        return _public_user(row)
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------- sessions

def create_session(user_id: int, conn=None) -> str:
    """Issue a new opaque session token for the user (one active session per user).

    Mirrors the lecture's upsert: a fresh login replaces the previous session row.
    """
    token = secrets.token_urlsafe(32)
    own = conn is None
    conn = conn or get_db()
    try:
        conn.execute(
            "INSERT INTO sessions (user_id, session_id, created_at) VALUES (?, ?, ?) "
            "ON DUPLICATE KEY UPDATE "
            "session_id = VALUES(session_id), created_at = VALUES(created_at)",
            (user_id, token, _now_iso()),
        )
        conn.commit()
        return token
    finally:
        if own:
            conn.close()


def get_user_by_session(token: str, conn=None):
    """Resolve a session token to its public user, or None."""
    if not token:
        return None
    own = conn is None
    conn = conn or get_db()
    try:
        row = conn.execute(
            "SELECT u.* FROM users u JOIN sessions s ON s.user_id = u.id "
            "WHERE s.session_id = ?",
            (token,),
        ).fetchone()
        return _public_user(row) if row else None
    finally:
        if own:
            conn.close()


def delete_session(token: str, conn=None) -> None:
    """Destroy a session (logout). No-op if the token is missing/unknown."""
    if not token:
        return
    own = conn is None
    conn = conn or get_db()
    try:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (token,))
        conn.commit()
    finally:
        if own:
            conn.close()


def list_users(search=None, limit=None, offset=0, conn=None) -> list:
    """Users with a computed post_count; optional name/email search; paginated."""
    own = conn is None
    conn = conn or get_db()
    try:
        sql = (
            "SELECT u.*, COUNT(p.id) AS post_count "
            "FROM users u LEFT JOIN posts p ON p.author_id = u.id"
        )
        params = []
        if search:
            sql += " WHERE LOWER(u.name) LIKE ? OR LOWER(u.email) LIKE ?"
            like = f"%{search.strip().lower()}%"
            params += [like, like]
        sql += " GROUP BY u.id ORDER BY post_count DESC, u.name ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params += [limit, offset or 0]
        rows = conn.execute(sql, params).fetchall()
        return [{**_public_user(r), "post_count": r["post_count"]} for r in rows]
    finally:
        if own:
            conn.close()


def get_user_profile(user_id: int, viewer_id=None, conn=None):
    """Return {user, posts, followers_count, following_count, is_following} or None.

    `viewer_id` is the currently logged-in user (if any); `is_following` reflects
    whether that viewer follows this profile.
    """
    own = conn is None
    conn = conn or get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return None
        rows = conn.execute(
            POSTS_SELECT + " WHERE p.author_id = ? ORDER BY p.created_at DESC", (user_id,)
        ).fetchall()
        followers = conn.execute(
            "SELECT COUNT(*) AS c FROM follows WHERE followee_id = ?", (user_id,)
        ).fetchone()["c"]
        following = conn.execute(
            "SELECT COUNT(*) AS c FROM follows WHERE follower_id = ?", (user_id,)
        ).fetchone()["c"]
        is_following = False
        if viewer_id and viewer_id != user_id:
            is_following = conn.execute(
                "SELECT 1 FROM follows WHERE follower_id = ? AND followee_id = ?",
                (viewer_id, user_id),
            ).fetchone() is not None
        return {
            "user": _public_user(user),
            "posts": [_post_to_dict(conn, r) for r in rows],
            "followers_count": followers,
            "following_count": following,
            "is_following": is_following,
        }
    finally:
        if own:
            conn.close()


def update_profile(user_id: int, bio=None, avatar_url=None, conn=None) -> dict:
    """Patch the editable profile fields; only provided (non-None) fields change."""
    own = conn is None
    conn = conn or get_db()
    try:
        sets, params = [], []
        if bio is not None:
            sets.append("bio = ?")
            params.append(bio)
        if avatar_url is not None:
            sets.append("avatar_url = ?")
            params.append(avatar_url)
        if sets:
            params.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", params)
            conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return _public_user(row)
    finally:
        if own:
            conn.close()


# ---------------------------------------------------------------------- follows

def user_exists(user_id: int, conn=None) -> bool:
    own = conn is None
    conn = conn or get_db()
    try:
        return conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is not None
    finally:
        if own:
            conn.close()


def follow_user(follower_id: int, followee_id: int, conn=None) -> None:
    """Create a follow edge (idempotent). Self-follow is rejected by the caller/CHECK."""
    own = conn is None
    conn = conn or get_db()
    try:
        conn.execute(
            "INSERT IGNORE INTO follows (follower_id, followee_id, created_at) "
            "VALUES (?, ?, ?)",
            (follower_id, followee_id, _now_iso()),
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def unfollow_user(follower_id: int, followee_id: int, conn=None) -> None:
    own = conn is None
    conn = conn or get_db()
    try:
        conn.execute(
            "DELETE FROM follows WHERE follower_id = ? AND followee_id = ?",
            (follower_id, followee_id),
        )
        conn.commit()
    finally:
        if own:
            conn.close()


# ------------------------------------------------------------------------ posts

def list_posts(limit=None, offset=0, follower_id=None, conn=None) -> list:
    """Newest-first feed, paginated. ISO timestamps sort lexically == chronologically.

    When `follower_id` is given, restricts the feed to posts authored by users that
    `follower_id` follows (the "individual"/following feed).
    """
    own = conn is None
    conn = conn or get_db()
    try:
        sql = POSTS_SELECT
        params = []
        if follower_id is not None:
            sql += (
                " JOIN follows f ON f.followee_id = p.author_id AND f.follower_id = ?"
            )
            params.append(follower_id)
        sql += " ORDER BY p.created_at DESC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params += [limit, offset or 0]
        rows = conn.execute(sql, params).fetchall()
        return [_post_to_dict(conn, r) for r in rows]
    finally:
        if own:
            conn.close()


def create_post(author_id: int, title: str, body: str, defendant: str,
                charges=None, image_url=None, conn=None) -> dict:
    own = conn is None
    conn = conn or get_db()
    try:
        cur = conn.execute(
            "INSERT INTO posts (title, body, defendant, image_url, author_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title.strip(), body.strip(), defendant.strip(), image_url,
             author_id, _now_iso()),
        )
        post_id = cur.lastrowid
        for charge in (charges or []):
            conn.execute(
                "INSERT INTO post_charges (post_id, charge) VALUES (?, ?)", (post_id, charge)
            )
        conn.commit()
        row = conn.execute(POSTS_SELECT + " WHERE p.id = ?", (post_id,)).fetchone()
        return _post_to_dict(conn, row)
    finally:
        if own:
            conn.close()

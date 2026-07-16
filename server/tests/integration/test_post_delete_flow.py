"""Integration tests — the post-delete flow (the pyramid middle).

Each test drives the REAL Flask endpoints through the test client, so one test
exercises several units at once: the route handler + require_auth + the services
layer + storage. The storage is a throwaway SQLite DB injected by conftest, so
these stay fast and hermetic while still testing the seams between units —
exactly what integration tests are for.

Every test follows Arrange -> Act -> Assert.
"""
import pytest


def _signup(client, name="Alice", email="alice@runi.ac.il", password="secret123"):
    resp = client.post("/api/auth/signup", json={"name": name, "email": email, "password": password})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()["user"]


def _create_post(client, title="תביעה לדוגמה", defendant="הנתבע", body="גוף התביעה"):
    resp = client.post(
        "/api/posts",
        json={"title": title, "body": body, "defendant": defendant},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def _post_ids(client) -> set:
    resp = client.get("/api/posts")
    assert resp.status_code == 200
    return {p["id"] for p in resp.get_json()}


@pytest.mark.integration
def test_owner_can_delete_their_own_post(client):
    # Arrange — signed-in author with one post.
    _signup(client)
    post = _create_post(client)

    # Act — the same (cookie-authenticated) user deletes it.
    resp = client.delete(f"/api/posts/{post['id']}")

    # Assert — 200 ok, and it's gone from the feed.
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    assert post["id"] not in _post_ids(client)


@pytest.mark.integration
def test_deleting_another_users_post_is_forbidden(client, db_path):
    # Arrange — user A creates a post.
    _signup(client, name="Alice", email="alice@runi.ac.il")
    post = _create_post(client)

    # Act — user B (a separate session, same underlying DB file) tries to delete it.
    from app import create_app
    other_app = create_app()
    other_app.config.update(TESTING=True)
    other_client = other_app.test_client()
    _signup(other_client, name="Bob", email="bob@runi.ac.il")
    resp = other_client.delete(f"/api/posts/{post['id']}")

    # Assert — 403 with an error, and the post is untouched (the server-side
    # ownership check, not just the unit-level one, is what's under test here).
    assert resp.status_code == 403
    assert "error" in resp.get_json()
    assert post["id"] in _post_ids(client)


@pytest.mark.integration
def test_deleting_a_nonexistent_post_returns_not_found(client):
    # Arrange — a logged-in user, but no post with this id was ever created.
    _signup(client)

    # Act
    resp = client.delete("/api/posts/999999")

    # Assert — 404 with an error message.
    assert resp.status_code == 404
    assert "error" in resp.get_json()


@pytest.mark.integration
def test_deleting_a_post_without_a_session_is_rejected(client):
    # Arrange — a real post exists, created by a logged-in author...
    _signup(client)
    post = _create_post(client)
    # ...then log out, so the next request carries no session.
    client.post("/api/auth/logout")

    # Act — attempt to delete it while unauthenticated.
    resp = client.delete(f"/api/posts/{post['id']}")

    # Assert — require_auth rejects it with 401, and the post survives.
    assert resp.status_code == 401
    assert "error" in resp.get_json()
    assert post["id"] in _post_ids(client)

# -*- coding: utf-8 -*-
"""Who may call what, swept from the routing table rather than listed by hand.

Every other file here tests the endpoints it is about. This one exists for the
endpoints nobody wrote a test for - it walks `app.url_map` and asserts a
property of each route, so an endpoint added next month without a permission
test shows up as a failure rather than as silence.

The property is that every route declares its own answer to "who is this for".
There are exactly three decorators (`require_auth`, `require_admin`,
`optional_auth`) and one deliberate exemption list, so a route that carries
none of them is either public on purpose - and named below - or an oversight.

Two of the three write to `g` and the difference between two of the answers is
load-bearing:

    anonymous       401, meaning "sign in"
    signed in, not admin   403, meaning "signing in will not help"

Collapsing those sends an ordinary user round a login loop that can never
succeed, so the admin sweep checks both.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

# Routes that are public by design, with the reason each one is.
#
# Listed by endpoint name rather than by rule, so renaming a URL does not
# silently re-exempt something, and adding a route does not inherit an
# exemption from a neighbour.
PUBLIC_BY_DESIGN = {
    # Liveness. A probe that needed a session could not report that the
    # database is down, because resolving the session is the thing that fails.
    "health.health",
    # The /about page's cast. Nothing here is anybody's private data - it is
    # the site's own dramatis personae.
    "trial.list_agents",
    # Profile pictures and evidence photos on public filings. Requiring a
    # session would break every signed-out page.
    "uploads.serve_image",
    # Signing up, signing in, and signing out cannot themselves require a
    # session. `/auth/me` is `optional_auth` and answers null for anonymous.
    "auth.signup",
    "auth.login",
    "auth.logout",
    "auth.request_password_reset",
    "auth.confirm_password_reset",
    # Checking whether a reset link is still live, so the page can show the
    # form or the expired notice. It is reached from an email, which is by
    # definition a context with no session.
    "auth.validate_password_reset",
}

# The path parameters a swept route needs, filled with values that exist for
# nothing - the point is the permission check, which runs before the lookup.
PARAMETERS = {
    "case_id": 999_999,
    "comment_id": 999_999,
    "user_id": 999_999,
    "conversation_id": 999_999,
    "report_id": 999_999,
    "target_id": 999_999,
    "target_type": "case",
    "name": "deadbeefdeadbeefdeadbeefdeadbeef.png",
}


def _routes(app):
    """Every API rule, with a concrete URL and the methods it answers."""
    found = []
    for rule in app.url_map.iter_rules():
        if not str(rule).startswith("/api/"):
            continue
        methods = sorted(rule.methods - {"HEAD", "OPTIONS"})
        values = {name: PARAMETERS[name] for name in rule.arguments}
        found.append((rule.endpoint, rule.rule, methods, values))
    return sorted(found)


def _url(rule: str, values: dict) -> str:
    for name, value in values.items():
        rule = rule.replace(f"<int:{name}>", str(value)).replace(f"<{name}>", str(value))
    return rule


def _is_guarded(app, endpoint: str) -> bool:
    """Whether this view carries one of the three authorisation decorators.

    All three use `functools.wraps`, which keeps the original `__name__` and
    `__doc__` - so a wrapped view is indistinguishable from a bare one by name,
    and the only reliable trace is the `__wrapped__` attribute `wraps` sets.
    Nothing else in `app/api` decorates a view, so its presence is exactly the
    question being asked.

    Which of the three it is does not matter here: the sweeps below establish
    that behaviourally, by calling the route and reading the status.
    """
    return hasattr(app.view_functions[endpoint], "__wrapped__")


# --- the sweep --------------------------------------------------------------


def test_the_sweep_actually_finds_the_routes(app):
    """A guard on the guard.

    A sweep over an empty list is a green test that ran zero times, and these
    all iterate `url_map`. The endpoints named are the ones the tests below
    most rely on being present.
    """
    endpoints = {endpoint for endpoint, _, _, _ in _routes(app)}

    assert len(endpoints) > 30
    for expected in ("auth.login", "moderation.admin_queue", "cases.create_case", "social.toggle_like"):
        assert expected in endpoints


def test_every_route_declares_who_it_is_for(app):
    """No route is accidentally public.

    Either it carries one of the three decorators - which `functools.wraps`
    hides from `__name__` but not from `__wrapped__` - or it is named in
    PUBLIC_BY_DESIGN with the reason it is public. Anything else is a route
    somebody forgot to think about.
    """
    undeclared = [
        endpoint
        for endpoint, _, _, _ in _routes(app)
        if not _is_guarded(app, endpoint) and endpoint not in PUBLIC_BY_DESIGN
    ]

    assert undeclared == []


def test_the_exemption_list_has_no_dead_entries(app):
    """An exemption for a route that no longer exists is an exemption waiting
    to be inherited by an unrelated endpoint that happens to reuse the name."""
    endpoints = {endpoint for endpoint, _, _, _ in _routes(app)}

    assert PUBLIC_BY_DESIGN <= endpoints


def test_no_mutating_route_is_reachable_without_a_session(app, client):
    """The sweep that would catch a new endpoint with no decorator on it.

    Every POST, PATCH, PUT and DELETE under /api, called anonymously, must
    answer 401 - except signing up and signing in, which cannot require the
    thing they exist to issue.
    """
    allowed = {"auth.signup", "auth.login", "auth.logout",
               "auth.request_password_reset", "auth.confirm_password_reset"}

    for endpoint, rule, methods, values in _routes(app):
        if endpoint in allowed:
            continue
        for method in methods:
            if method == "GET":
                continue
            response = client.open(_url(rule, values), method=method, json={})
            assert response.status_code == 401, f"{method} {rule} ({endpoint})"


def test_every_admin_route_answers_401_anonymously_and_403_to_a_user(
    app, client, make_user, signed_in
):
    """Two different refusals, and the difference is what the client renders.

    401 means "sign in"; 403 means "signing in will not help". A route that
    answered 403 to an anonymous request would leave a signed-out moderator
    with no way to know they simply needed to log in.
    """
    admin_routes = [
        (rule, methods, values)
        for endpoint, rule, methods, values in _routes(app)
        if "/api/admin/" in rule
    ]
    assert len(admin_routes) >= 8

    for rule, methods, values in admin_routes:
        for method in methods:
            assert client.open(_url(rule, values), method=method, json={}).status_code == 401, rule

    signed_in(make_user("משתמש רגיל", "ordinary@lolsuit.test"))

    for rule, methods, values in admin_routes:
        for method in methods:
            assert client.open(_url(rule, values), method=method, json={}).status_code == 403, rule


def test_an_admin_reaches_every_admin_route(app, client, admin, signed_in):
    """The other side, so the check above cannot be satisfied by refusing all.

    404 and 400 are fine here - the ids are deliberately nonexistent. What must
    not appear is 401 or 403, which would mean the route is unreachable even
    to the people it is for.
    """
    signed_in(admin)

    for endpoint, rule, methods, values in _routes(app):
        if "/api/admin/" not in rule:
            continue
        for method in methods:
            status = client.open(_url(rule, values), method=method, json={}).status_code
            assert status not in (401, 403), f"{method} {rule} -> {status}"


def test_a_banned_user_is_locked_out_of_everything_that_needs_a_session(
    app, db, client, make_user, signed_in
):
    """A ban bites on the very next request, on every route at once.

    `resolve_session` joins on `users.status = 'active'`, so this is one check
    rather than a rule each endpoint has to remember - and the sweep is what
    proves no endpoint found a way around it.
    """
    user = make_user("מושעה", "banned@lolsuit.test")
    signed_in(user)
    assert client.get("/api/auth/me").get_json()["user"] is not None

    db.execute("UPDATE users SET status = 'banned' WHERE id = %s", (user["id"],))
    db.commit()

    checked = 0
    for endpoint, rule, methods, values in _routes(app):
        if endpoint in PUBLIC_BY_DESIGN or not _is_guarded(app, endpoint):
            continue
        for method in methods:
            if method != "POST":
                continue
            status = client.open(_url(rule, values), method=method, json={}).status_code
            if endpoint.startswith("auth."):
                continue
            assert status == 401, f"{method} {rule} -> {status}"
            checked += 1

    assert checked > 5


def test_an_optional_auth_route_works_signed_out_and_says_more_signed_in(
    client, app, db, make_user, signed_in, make_case
):
    """The third decorator, which is neither open nor closed.

    The feed works anonymously and tells a signed-in reader which cases they
    have already liked - so "works signed out" and "is the same signed out"
    are different claims, and only the first is true.
    """
    reader = make_user("קורא", "reader@lolsuit.test")
    author = make_user("תובע", "author@lolsuit.test")
    case_id = make_case(author["id"])

    anonymous = client.get("/api/cases").get_json()["cases"]
    assert [case["id"] for case in anonymous] == [case_id]
    assert anonymous[0]["viewer_has_liked"] is False

    signed_in(reader)
    client.post(f"/api/cases/{case_id}/like")

    seen = client.get("/api/cases").get_json()["cases"]
    assert seen[0]["viewer_has_liked"] is True

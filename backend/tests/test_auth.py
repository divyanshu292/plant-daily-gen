"""Sign-in, sessions, who may do what, user management and the activity log
(auth.py and the auth routes in main.py), with an in-memory database."""

from __future__ import annotations

import asyncio
import hashlib
import io
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from PIL import Image

import auth
import extract
import main
from helpers import PAGE_1, USER_PASSWORD, add_user, build_workbook, load_report, sign_in

NEW_PASSWORD = "a brand new secret"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "db", AsyncMongoMockClient()["ttps_test"])
    with TestClient(main.app) as c:
        yield c


def browser() -> TestClient:
    """Another device: the same app, its own cookies."""
    return TestClient(main.app)


def login(client, email: str, password: str = USER_PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def stored(email: str) -> dict:
    return run(main.db["users"].find_one({"email": email}))


def actions(client, path: str = "/api/auth/activity") -> list[str]:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return [a["action"] for a in response.json()]


def texts(client, path: str = "/api/auth/activity") -> list[str]:
    return [a["text"] for a in client.get(path).json()]


def later(monkeypatch, **delta) -> None:
    """Move the server's clock forward."""
    moved = datetime.now(timezone.utc) + timedelta(**delta)
    monkeypatch.setattr(main, "_utcnow", lambda: moved)


# --- auth.py ----------------------------------------------------------------------------------

def test_password_hash_format_and_check():
    stored_hash = auth.hash_password("s3cret-pass")
    scheme, n, r, p, salt, digest = stored_hash.split("$")
    assert (scheme, n, r, p) == ("scrypt", "16384", "8", "1")
    assert auth.hash_password("s3cret-pass") != stored_hash  # a new salt each time
    assert auth.verify_password("s3cret-pass", stored_hash) is True
    assert auth.verify_password("s3cret-pasS", stored_hash) is False
    for broken in (None, "", "plain", "scrypt$16384$8$1$!!$!!", stored_hash.replace("scrypt", "md5")):
        assert auth.verify_password("s3cret-pass", broken) is False


def test_input_checks():
    assert auth.check_email("  Ravi.K@Plant.IN ") == "ravi.k@plant.in"
    assert auth.check_name("  Ravi Kumar ") == "Ravi Kumar"
    for check, bad, message in (
        (auth.check_email, "ravi", "valid email"), (auth.check_email, None, "valid email"),
        (auth.check_name, "   ", "Enter a name"), (auth.check_name, "x" * 81, "at most 80"),
        (auth.check_password, "short", "at least 8"), (auth.check_password, "x" * 129, "at most 128"),
        (auth.check_role, "super_admin", "admin or viewer"),
    ):
        with pytest.raises(auth.Invalid, match=message):
            check(bad)


# --- signing in and out -----------------------------------------------------------------------

def test_login_sets_a_session_cookie(client):
    add_user("viewer", email="ravi@plant.in", name="Ravi")
    response = login(client, "  RAVI@Plant.in ")  # case and spaces do not matter
    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert set(user) == {"id", "email", "name", "role", "createdAt", "lastLoginAt"}
    assert (user["email"], user["name"], user["role"]) == ("ravi@plant.in", "Ravi", "viewer")
    assert user["lastLoginAt"]

    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("ttps_session=")
    assert all(part in cookie for part in ("httponly", "path=/", "samesite=lax", f"max-age={30 * 24 * 3600}"))
    assert "secure" not in cookie  # plain http here

    # Only the token's hash is stored.
    token = client.cookies.get(auth.COOKIE)
    [session] = stored("ravi@plant.in")["sessions"]
    assert session["hash"] == hashlib.sha256(token.encode()).hexdigest() != token
    assert client.get("/api/auth/me").json() == {"user": user}
    assert actions(client) == ["login"]


def test_cookie_is_secure_behind_https(client):
    add_user("viewer")
    response = client.post("/api/auth/login", json={"email": "viewer@test.local", "password": USER_PASSWORD},
                           headers={"X-Forwarded-Proto": "https"})
    assert response.status_code == 200 and "secure" in response.headers["set-cookie"].lower()


def test_wrong_password_and_unknown_email_get_the_same_answer(client):
    add_user("admin")
    for email, password in (("admin@test.local", "not the password"), ("nobody@test.local", USER_PASSWORD)):
        response = login(client, email, password)
        assert response.status_code == 401
        assert response.json() == {"detail": "Wrong email or password"}
    assert stored("admin@test.local")["failedLogins"] == 1
    assert client.cookies.get(auth.COOKIE) is None
    for body in ({}, {"email": "admin@test.local"}, {"email": "", "password": "x"}, {"email": "a", "password": 5}):
        assert client.post("/api/auth/login", json=body).status_code == 400


def test_five_wrong_passwords_lock_the_account(client, monkeypatch):
    add_user("admin")
    for _ in range(4):
        assert login(client, "admin@test.local", "wrong password").status_code == 401
    response = login(client, "admin@test.local", "wrong password")
    assert response.status_code == 429
    assert response.json()["detail"] == "Too many attempts. Try again in 5 min."
    # Locked: even the right password is refused, without being checked.
    assert login(client, "admin@test.local").status_code == 429
    later(monkeypatch, minutes=2, seconds=30)
    assert login(client, "admin@test.local").json()["detail"] == "Too many attempts. Try again in 3 min."

    later(monkeypatch, minutes=5, seconds=1)
    assert login(client, "admin@test.local").status_code == 200
    doc = stored("admin@test.local")
    assert (doc["failedLogins"], doc["lockedUntil"]) == (0, None)


def test_a_success_resets_the_count(client):
    add_user("admin")
    for _ in range(4):
        login(client, "admin@test.local", "wrong password")
    assert login(client, "admin@test.local").status_code == 200
    for _ in range(4):
        assert login(client, "admin@test.local", "wrong password").status_code == 401


def test_logout_ends_the_session(client):
    sign_in(client, "viewer")
    token = client.cookies.get(auth.COOKIE)
    response = client.post("/api/auth/logout")
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert "ttps_session=" in response.headers["set-cookie"] and client.cookies.get(auth.COOKIE) is None
    assert stored("viewer@test.local")["sessions"] == []
    # The old token no longer works, even if a copy was kept.
    client.cookies.set(auth.COOKIE, token)
    assert client.get("/api/auth/me").status_code == 401
    assert [a["action"] for a in stored("viewer@test.local")["activity"]] == ["login", "logout"]
    # Without a session it still answers, and clears the cookie.
    assert browser().post("/api/auth/logout").json() == {"ok": True}


def test_sessions_expire_and_are_capped(client, monkeypatch):
    sign_in(client, "viewer")
    assert client.get("/api/entries").status_code == 200
    later(monkeypatch, days=30, seconds=1)
    assert client.get("/api/entries").json() == {"detail": "Sign in to continue"}

    # Signing in again drops the expired session; the newest ten are kept.
    for _ in range(11):
        assert login(browser(), "viewer@test.local").status_code == 200
    sessions = stored("viewer@test.local")["sessions"]
    assert len(sessions) == auth.SESSIONS_KEPT
    assert all(s["expiresAt"] > auth.iso(main._utcnow()) for s in sessions)


# --- who may do what --------------------------------------------------------------------------

OPEN_ROUTES = {"/api/health", "/api/live/record", "/api/auth/login", "/api/auth/logout"}
OWN_ACCOUNT = {("PATCH", "/api/auth/me"), ("POST", "/api/auth/password")}


def guards(route: APIRoute) -> set:
    found, todo = set(), list(route.dependant.dependencies)
    while todo:
        dependency = todo.pop()
        found.add(dependency.call)
        todo += dependency.dependencies
    return found


def test_every_api_route_needs_a_session():
    """A new route without one of the three dependencies fails here."""
    routes = [r for r in main.app.routes if isinstance(r, APIRoute) and r.path.startswith("/api")]
    assert {r.path for r in routes} >= OPEN_ROUTES | {"/api/users", "/api/entries"}
    for route in routes:
        if route.path in OPEN_ROUTES:
            assert main.require_user not in guards(route), route.path
            continue
        found = guards(route)
        assert main.require_user in found, f"{route.path} needs a session"
        writes = route.methods & {"POST", "PUT", "PATCH", "DELETE"}
        if writes and not {(m, route.path) for m in writes} <= OWN_ACCOUNT:
            assert found & {main.require_editor, main.require_super_admin}, f"{route.path} lets viewers write"
        if route.path.startswith("/api/users"):
            assert main.require_super_admin in found, route.path


def test_data_needs_a_session(client):
    for path in ("/api/entries", "/api/reports", "/api/analytics", "/api/config/2026", "/api/auth/me",
                 "/api/auth/activity", "/api/users"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json() == {"detail": "Sign in to continue"}
    client.cookies.set(auth.COOKIE, "made-up-token")
    assert client.get("/api/entries").status_code == 401
    assert client.put("/api/entries/2026-11-03", json={"u1Gen": 1}).status_code == 401
    assert client.get("/api/health").status_code == 200


def upload_page(client):
    return client.post("/api/reports", files={"file": ("page.jpg", b"not read", "image/jpeg")})


def import_book(client):
    return client.post("/api/import/workbook", files={"file": ("book.xlsx", b"not read", "application/octet-stream")})


def test_viewer_reads_but_cannot_write(client, monkeypatch):
    def no_reading(*args, **kwargs):
        raise AssertionError("a viewer's upload was read")

    monkeypatch.setattr(main.extract, "extract_report", no_reading)
    sign_in(client, "viewer")
    for path in ("/api/entries", "/api/reports", "/api/analytics", "/api/config/2026",
                 "/api/performance/2026-11-03", "/api/live/day"):
        assert client.get(path).status_code == 200, path
    assert client.get("/api/reports/nope").status_code == 404  # allowed to look, nothing there

    for response in (
        client.put("/api/entries/2026-11-03", json={"u1Gen": 1}),
        upload_page(client),
        client.post("/api/reports/any/confirm", json={}),
        client.put("/api/config/2026", json={"unitMw": 200}),
        import_book(client),
    ):
        assert response.status_code == 403
        assert response.json() == {"detail": "Your access is view only"}
    assert client.get("/api/users").json() == {"detail": "Only the super admin can manage users"}
    assert client.get("/api/entries").json() == []
    assert client.get("/api/config/2026").json()["unitMw"] == 210


def test_admin_writes_but_cannot_manage_users(client):
    admin = sign_in(client, "admin")
    assert client.put("/api/entries/2026-11-03", json={"u1Gen": 3.48, "gcv": 3400}).status_code == 200
    assert client.put("/api/entries/2026-11-03", json={"u1Gen": 3.48, "u2Gen": 3.6}).status_code == 200
    assert client.put("/api/config/2026", json={"unitMw": 200, "bogus": 1}).status_code == 200
    assert import_book(client).status_code == 422  # allowed; just not a workbook
    assert texts(client) == ["Changed FY 2026-27 unit MW", "Edited 3 Nov 2026: u2Gen",
                             "Edited 3 Nov 2026: u1Gen, gcv", "Signed in"]

    other = add_user("viewer")
    for response in (
        client.get("/api/users"),
        client.post("/api/users", json={"email": "x@y.in", "name": "X", "password": NEW_PASSWORD, "role": "admin"}),
        client.patch(f"/api/users/{other['id']}", json={"role": "admin"}),
        client.post(f"/api/users/{other['id']}/password", json={"password": NEW_PASSWORD}),
        client.delete(f"/api/users/{other['id']}"),
        client.get(f"/api/users/{other['id']}/activity"),
    ):
        assert response.status_code == 403
        assert response.json() == {"detail": "Only the super admin can manage users"}
    assert stored("viewer@test.local")["role"] == "viewer" and admin["role"] == "admin"


def test_uploads_imports_and_confirms_are_logged(client, monkeypatch):
    misread = load_report(PAGE_1)
    misread.r04_gen.unit1 = "3.43"  # the totals no longer add up: held for review
    readings = [misread, misread, load_report(PAGE_1)]

    async def reader(image, recheck=None):
        return extract.Extraction(report=readings.pop(0), model="fake", usage={})

    monkeypatch.setattr(main.extract, "extract_report", reader)
    sign_in(client, "admin")
    photo = io.BytesIO()
    Image.new("RGB", (1119, 1599), "white").save(photo, format="JPEG")
    page = {"file": ("page.jpg", photo.getvalue(), "image/jpeg")}
    held = client.post("/api/reports", files=page).json()
    assert held["status"] == "needs_review"
    assert client.post(f"/api/reports/{held['id']}/confirm", json={"entry": {"u1Gen": 3.48}}).status_code == 200
    assert client.post("/api/reports", files=page).json()["status"] == "saved"
    assert texts(client)[:3] == ["Uploaded the report for 3 Nov 2026 (saved)",
                                 "Confirmed the report for 3 Nov 2026",
                                 "Uploaded the report for 3 Nov 2026 (needs review)"]

    # 1 Nov is new; 3 Nov keeps the page's generation and gains the GCV, which the page does not carry.
    book = build_workbook({"2026-11-01": {"u1Gen": 3.48, "gcv": 3450}, "2026-11-03": {"u1Gen": 9.99, "gcv": 3450}})
    assert client.post("/api/import/workbook", files={"file": ("b.xlsx", book, "x")}).status_code == 200
    assert texts(client)[0] == "Imported FY 2026-27 workbook: 1 added, 1 updated"
    assert actions(client) == ["workbook_imported", "report_uploaded", "report_confirmed", "report_uploaded", "login"]


# --- the super admin --------------------------------------------------------------------------

def onboard(client, **fields):
    body = {"email": "ravi@plant.in", "name": "Ravi", "password": NEW_PASSWORD, "role": "viewer", **fields}
    return client.post("/api/users", json=body)


def test_super_admin_onboards_people(client):
    boss = sign_in(client, "super_admin", name="Boss")
    response = onboard(client, email="  Ravi@Plant.IN ", name="  Ravi ")
    assert response.status_code == 201, response.text
    ravi = response.json()["user"]
    assert set(ravi) == {"id", "email", "name", "role", "createdAt", "lastLoginAt"}
    assert (ravi["email"], ravi["name"], ravi["role"], ravi["lastLoginAt"]) == ("ravi@plant.in", "Ravi", "viewer", None)
    assert stored("ravi@plant.in")["createdBy"] == boss["id"]

    assert onboard(client, email="RAVI@plant.in").status_code == 409
    assert onboard(client, email="RAVI@plant.in").json()["detail"] == "Someone with this email already exists"
    for bad in ({"role": "super_admin"}, {"role": None}, {"email": "ravi"}, {"name": " "},
                {"password": "short"}, {"email": "new@plant.in", "role": "owner"}):
        assert onboard(client, **bad).status_code == 400, bad
    assert onboard(client, email="anu@plant.in", name="Anu", role="admin").status_code == 201

    # The super admin first, then by name; nothing private.
    people = client.get("/api/users").json()
    assert [p["name"] for p in people] == ["Boss", "Anu", "Ravi"]
    assert all(set(p) == set(ravi) for p in people)

    new = browser()
    assert login(new, "ravi@plant.in", NEW_PASSWORD).json()["user"]["role"] == "viewer"
    assert texts(new) == ["Signed in", "Account created by Boss"]
    assert texts(client)[:2] == ["Onboarded Anu (anu@plant.in) as admin", "Onboarded Ravi (ravi@plant.in) as viewer"]
    assert actions(client, f"/api/users/{ravi['id']}/activity") == ["login", "account_created"]
    assert len(client.get(f"/api/users/{ravi['id']}/activity", params={"limit": 1}).json()) == 1
    assert client.get("/api/users/nope/activity").status_code == 404


def test_role_change_takes_effect_at_once(client):
    sign_in(client, "super_admin", name="Boss")
    ravi = onboard(client).json()["user"]
    phone = browser()
    login(phone, "ravi@plant.in", NEW_PASSWORD)
    assert phone.put("/api/entries/2026-11-03", json={"u1Gen": 1}).status_code == 403

    response = client.patch(f"/api/users/{ravi['id']}", json={"role": "admin"})
    assert response.status_code == 200 and response.json()["user"]["role"] == "admin"
    assert phone.put("/api/entries/2026-11-03", json={"u1Gen": 1}).status_code == 200  # same session

    assert client.patch(f"/api/users/{ravi['id']}", json={"name": "Ravi Kumar"}).json()["user"]["name"] == "Ravi Kumar"
    assert client.patch(f"/api/users/{ravi['id']}", json={"role": "super_admin"}).status_code == 400
    assert client.patch(f"/api/users/{ravi['id']}", json={"email": "new@x.in"}).json()["user"]["email"] == "ravi@plant.in"
    assert client.patch("/api/users/nope", json={"role": "admin"}).status_code == 404
    assert texts(client)[:2] == ["Renamed Ravi to Ravi Kumar", "Made Ravi an admin"]
    assert texts(phone)[:3] == ["Name changed to Ravi Kumar by Boss", "Edited 3 Nov 2026: u1Gen",
                                "Access changed to admin by Boss"]


def test_setting_a_password_ends_their_sessions(client):
    sign_in(client, "super_admin", name="Boss")
    ravi = onboard(client).json()["user"]
    phone = browser()
    login(phone, "ravi@plant.in", NEW_PASSWORD)
    for _ in range(5):
        login(browser(), "ravi@plant.in", "forgotten it")  # now locked

    assert client.post(f"/api/users/{ravi['id']}/password", json={"password": "short"}).status_code == 400
    assert client.post("/api/users/nope/password", json={"password": "long enough"}).status_code == 404
    response = client.post(f"/api/users/{ravi['id']}/password", json={"password": "set by the boss"})
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert phone.get("/api/auth/me").status_code == 401
    assert login(browser(), "ravi@plant.in", NEW_PASSWORD).status_code == 401  # the lock is lifted too
    assert login(phone, "ravi@plant.in", "set by the boss").status_code == 200
    assert texts(phone)[:2] == ["Signed in", "Password set by Boss"]
    assert texts(client)[0] == "Set a new password for Ravi"


def test_removing_someone_signs_them_out(client):
    sign_in(client, "super_admin")
    ravi = onboard(client).json()["user"]
    phone = browser()
    login(phone, "ravi@plant.in", NEW_PASSWORD)
    response = client.delete(f"/api/users/{ravi['id']}")
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert phone.get("/api/entries").status_code == 401
    assert [p["email"] for p in client.get("/api/users").json()] == ["super_admin@test.local"]
    assert client.delete(f"/api/users/{ravi['id']}").status_code == 404
    assert texts(client)[0] == "Removed Ravi (ravi@plant.in)"


def test_the_super_admin_cannot_be_changed_through_users(client):
    boss = sign_in(client, "super_admin")
    # Another super admin cannot be made through the API; one put in the database is protected too.
    other = add_user("super_admin", email="other@test.local")
    for target, own in ((boss, True), (other, False)):
        url = f"/api/users/{target['id']}"
        assert client.patch(url, json={"role": "viewer"}).json()["detail"] == "The super admin's access cannot change"
        assert client.patch(url, json={"name": "New"}).status_code == 400
        assert client.post(f"{url}/password", json={"password": NEW_PASSWORD}).json()["detail"] == \
            "Use Account to change your own password"
        response = client.delete(url)
        assert response.status_code == 400
        assert response.json()["detail"] == ("You cannot remove yourself" if own else "The super admin cannot be removed")
    assert stored("super_admin@test.local")["role"] == stored("other@test.local")["role"] == "super_admin"
    assert client.get("/api/auth/me").status_code == 200


# --- your own account -------------------------------------------------------------------------

def test_change_own_name(client):
    sign_in(client, "viewer", name="Ravi")
    response = client.patch("/api/auth/me", json={"name": "  Ravi K  ", "email": "else@x.in", "role": "admin"})
    assert response.status_code == 200
    assert response.json()["user"] == {**client.get("/api/auth/me").json()["user"], "name": "Ravi K"}
    assert (stored("viewer@test.local")["name"], stored("viewer@test.local")["role"]) == ("Ravi K", "viewer")
    assert client.patch("/api/auth/me", json={"name": ""}).status_code == 400
    assert client.patch("/api/auth/me", json={}).status_code == 400
    assert texts(client) == ["Changed name to Ravi K", "Signed in"]


def test_change_own_password(client):
    sign_in(client, "viewer")
    laptop = browser()
    login(laptop, "viewer@test.local")

    wrong = client.post("/api/auth/password", json={"currentPassword": "not it", "newPassword": NEW_PASSWORD})
    assert wrong.status_code == 400 and wrong.json()["detail"] == "Current password is wrong"
    short = client.post("/api/auth/password", json={"currentPassword": USER_PASSWORD, "newPassword": "short"})
    assert short.json()["detail"] == "Password must be at least 8 characters"
    assert laptop.get("/api/auth/me").status_code == 200

    done = client.post("/api/auth/password", json={"currentPassword": USER_PASSWORD, "newPassword": NEW_PASSWORD})
    assert done.status_code == 200 and done.json() == {"ok": True}
    assert client.get("/api/auth/me").status_code == 200  # this session stays
    assert laptop.get("/api/auth/me").status_code == 401  # every other one ends
    assert login(browser(), "viewer@test.local").status_code == 401
    assert login(browser(), "viewer@test.local", NEW_PASSWORD).status_code == 200
    assert actions(client)[:2] == ["login", "password_changed"]


def test_activity_is_newest_first_and_capped(client):
    user = sign_in(client, "viewer")

    async def many():
        for i in range(auth.ACTIVITY_KEPT + 5):
            await main._log(user["id"], "test", f"entry {i}")

    run(many())
    activity = client.get("/api/auth/activity", params={"limit": 500}).json()
    assert len(activity) == auth.ACTIVITY_KEPT == len(stored("viewer@test.local")["activity"])
    assert activity[0]["text"] == f"entry {auth.ACTIVITY_KEPT + 4}" and activity[-1]["text"] == "entry 5"
    assert set(activity[0]) == {"at", "action", "text"}
    assert [a["text"] for a in client.get("/api/auth/activity", params={"limit": 2}).json()] == \
        [f"entry {auth.ACTIVITY_KEPT + 4}", f"entry {auth.ACTIVITY_KEPT + 3}"]
    assert len(client.get("/api/auth/activity", params={"limit": 0}).json()) == 1


def test_a_failed_activity_write_does_not_fail_the_request(monkeypatch, capsys):
    class Broken:
        def __getitem__(self, name):
            raise RuntimeError("database gone")

    monkeypatch.setattr(main, "db", Broken())
    run(main._log("someone", "login", "Signed in"))  # no exception
    assert "Could not record activity login" in capsys.readouterr().out


# --- the super admin seed ---------------------------------------------------------------------

def super_admins() -> list[dict]:
    return run(main.db["users"].find({"role": "super_admin"}).to_list(None))


def test_super_admin_is_seeded_once_and_never_overwritten(monkeypatch):
    monkeypatch.setattr(main, "db", AsyncMongoMockClient()["ttps_test"])
    run(main._seed_super_admin())
    assert super_admins() == []  # no settings, nobody

    monkeypatch.setenv("SUPERADMIN_EMAIL", " Boss@Plant.IN ")
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "boss password")
    with TestClient(main.app):  # at startup
        pass
    run(main._seed_super_admin())
    [boss] = super_admins()
    assert (boss["email"], boss["name"]) == ("boss@plant.in", "Super admin")
    assert auth.verify_password("boss password", boss["passwordHash"])

    # Changed settings do not touch the existing super admin or add another.
    monkeypatch.setenv("SUPERADMIN_EMAIL", "new@plant.in")
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "another password")
    run(main._seed_super_admin())
    assert super_admins() == [boss]


def test_super_admin_is_seeded_at_sign_in(monkeypatch):
    monkeypatch.setattr(main, "db", AsyncMongoMockClient()["ttps_test"])
    c = browser()  # no startup, as on a serverless host
    assert login(c, "boss@plant.in", "boss password").status_code == 401
    monkeypatch.setenv("SUPERADMIN_EMAIL", "boss@plant.in")
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "boss password")
    monkeypatch.setenv("SUPERADMIN_NAME", "Plant Head")
    response = login(c, "boss@plant.in", "boss password")
    assert response.status_code == 200
    assert (response.json()["user"]["role"], response.json()["user"]["name"]) == ("super_admin", "Plant Head")
    assert len(super_admins()) == 1


def test_seed_leaves_an_existing_user_with_that_email_alone(monkeypatch):
    monkeypatch.setattr(main, "db", AsyncMongoMockClient()["ttps_test"])
    add_user("viewer", email="boss@plant.in")
    monkeypatch.setenv("SUPERADMIN_EMAIL", "boss@plant.in")
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "boss password")
    run(main._seed_super_admin())
    assert super_admins() == [] and stored("boss@plant.in")["role"] == "viewer"
    assert auth.verify_password(USER_PASSWORD, stored("boss@plant.in")["passwordHash"])


# --- the scheduler's route --------------------------------------------------------------------

def test_live_record_needs_only_its_key(client, monkeypatch):
    feed = [{"station": f"Power Generation Unit-{u}", "readings": {"power": 150.0}, "units": {"power": "MW"},
             "timestamp": "12-Nov-2026 20:55"} for u in (1, 2)]

    async def portal(self, request, *args, **kwargs):
        return httpx.Response(200, json=feed, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", portal)
    monkeypatch.setattr(main, "_ist_now", lambda: datetime(2026, 11, 12, 21, 0, tzinfo=main.IST))
    monkeypatch.setattr(main, "LIVE_RETENTION_DAYS", 365 * 100)  # mongomock's TTL uses the real clock
    monkeypatch.setattr(main, "live_cache", {"data": None, "fetched_at": 0.0})
    monkeypatch.setenv("LIVE_RECORD_KEY", "s3cret")

    assert client.cookies.get(auth.COOKIE) is None
    assert client.get("/api/live/record").status_code == 401  # the key, not a session, is what it needs
    response = client.get("/api/live/record", params={"key": "s3cret"})
    assert response.status_code == 200 and response.json()["recorded"] is True
    assert client.post("/api/live/record", headers={"X-Record-Key": "s3cret"}).status_code == 200

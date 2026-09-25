import io
import unicodedata

import pytest
from PIL import Image

from tests.conftest import ADMIN, login, signup

SOLUTION = {"problem_title": "근과 계수", "steps": ["a+b=4", "ab=3"], "final_answer": "10", "tip": ""}


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (500, 300), "white").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def fake_ai(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    calls = {"n": 0, "fail": False}

    def fake(image_bytes, mime_type, api_key, solve_style):
        calls["n"] += 1
        if calls["fail"]:
            return {"error": True, "error_message": "boom"}
        return dict(SOLUTION)

    monkeypatch.setattr("server.main.solve_problem_with_gemini", fake)
    return calls


def solve(client):
    return client.post("/api/solve", files={"image": ("p.png", png(), "image/png")}, data={"mode": "killer_tutor"})


# ---------- 관리자 계정 ----------
def test_admin_created_from_env_and_unlimited(client, fake_ai):
    res = login(client, *ADMIN)
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["role"] == "admin" and body["usage"]["limit"] is None
    for _ in range(5):  # 기본 한도(3)를 넘어도 관리자는 제한 없음
        assert solve(client).status_code == 200


def test_no_admin_without_password(make_client):
    client = make_client(admin_password="")
    assert login(client, ADMIN[0], "").status_code == 401
    assert login(client, *ADMIN).status_code == 401


def test_admin_password_follows_env(make_client):
    c1 = make_client()
    assert login(c1, *ADMIN).status_code == 200
    assert c1.get("/api/auth/me").status_code == 200
    c2 = make_client(admin_password="rotated-password")  # 같은 DB로 재시작 + 비밀번호 교체
    assert login(c2, *ADMIN).status_code == 401
    assert login(c2, ADMIN[0], "rotated-password").status_code == 200
    assert c1.get("/api/auth/me").status_code == 401  # 기존 로그인은 끊김


def test_admin_cannot_change_password_in_app(client):
    login(client, *ADMIN)
    res = client.post("/api/auth/password", json={"current_password": ADMIN[1], "new_password": "something-else"})
    assert res.status_code == 400 and "ADMIN_PASSWORD" in res.json()["detail"]


# ---------- 가입/로그인 ----------
def test_signup_validation_and_duplicates(client):
    bad = client.post("/api/auth/signup", json={"username": "a", "password": "password123"})
    assert bad.status_code == 400
    short = client.post("/api/auth/signup", json={"username": "학생", "password": "short"})
    assert short.status_code == 400
    signup(client, "Student", "password123")
    dup = client.post("/api/auth/signup", json={"username": "student", "password": "password123"})
    assert dup.status_code == 400
    # 자모 분리(NFD)로 입력된 관리자 아이디도 같은 아이디로 취급
    nfd = unicodedata.normalize("NFD", ADMIN[0])
    assert client.post("/api/auth/signup", json={"username": nfd, "password": "password123"}).status_code == 400


def test_login_logout_and_cookie_flags(client):
    signup(client, "학생2", "password123")
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    res = login(client, "학생2", "password123")
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/auth/me").json()["user"]["username"] == "학생2"
    assert login(client, "학생2", "wrong-password").json()["detail"] == login(client, "없는사람", "x").json()["detail"]


def test_login_throttled_after_repeated_failures(client):
    signup(client, "학생3", "password123")
    for _ in range(5):
        assert login(client, "학생3", "wrong").status_code == 401
    assert login(client, "학생3", "password123").status_code == 429


def test_change_password(client):
    signup(client, "학생4", "password123")
    assert client.post("/api/auth/password", json={"current_password": "nope", "new_password": "newpassword1"}).status_code == 400
    assert client.post("/api/auth/password", json={"current_password": "password123", "new_password": "newpassword1"}).status_code == 200
    assert client.get("/api/auth/me").status_code == 200  # 현재 기기는 새 세션으로 유지
    assert login(client, "학생4", "newpassword1").status_code == 200


def test_signup_can_be_disabled(make_client):
    client = make_client(allow_signup=False)
    assert client.post("/api/auth/signup", json={"username": "학생", "password": "password123"}).status_code == 403


def test_protected_endpoints_require_login(client):
    assert solve(client).status_code == 401
    assert client.get("/api/history").status_code == 401
    assert client.get("/api/admin/users").status_code == 401


def test_cross_origin_post_blocked(client):
    res = client.post(
        "/api/auth/login", json={"username": ADMIN[0], "password": ADMIN[1]}, headers={"Origin": "https://evil.example"}
    )
    assert res.status_code == 403


# ---------- 사용량 한도 ----------
def test_daily_limit_and_refund_on_failure(client, fake_ai):
    signup(client)
    fake_ai["fail"] = True
    assert solve(client).status_code == 502  # 실패는 한도에서 차감되지 않음
    fake_ai["fail"] = False
    for i in range(3):
        res = solve(client)
        assert res.status_code == 200 and res.json()["usage"] == {"used": i + 1, "limit": 3}
    res = solve(client)
    assert res.status_code == 429 and "3회" in res.json()["detail"]
    assert fake_ai["n"] == 4  # 한도 초과 시 AI를 호출하지 않음


# ---------- 풀이 기록 ----------
def test_history_roundtrip_and_isolation(make_client, fake_ai):
    a = make_client()
    signup(a, "학생A", "password123")
    sid = solve(a).json()["solve_id"]

    items = a.get("/api/history").json()["items"]
    assert [i["id"] for i in items] == [sid] and items[0]["final_answer"] == "10"
    thumb = a.get(f"/api/history/{sid}/image?thumb=true")
    assert thumb.status_code == 200 and max(Image.open(io.BytesIO(thumb.content)).size) <= 320

    res = a.post("/api/render", data={"solve_id": sid, "layout": "notebook", "pen": "red", "seed": 5})
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    detail = a.get(f"/api/history/{sid}").json()
    assert detail["style"]["layout"] == "notebook" and detail["style"]["pen"] == "red" and detail["style"]["seed"] == 5
    assert detail["solution"]["steps"] == ["a+b=4", "ab=3"]

    b = make_client()
    signup(b, "학생B", "password123")
    assert b.get(f"/api/history/{sid}").status_code == 404
    assert b.post("/api/render", data={"solve_id": sid}).status_code == 404
    assert b.delete(f"/api/history/{sid}").status_code == 404

    assert a.delete(f"/api/history/{sid}").status_code == 200
    assert a.get("/api/history").json()["items"] == []


def test_history_keeps_only_recent(make_client, fake_ai):
    client = make_client(history_limit=2, daily_solve_limit=10)
    signup(client)
    ids = [solve(client).json()["solve_id"] for _ in range(3)]
    assert [i["id"] for i in client.get("/api/history").json()["items"]] == ids[:0:-1]


# ---------- 관리자 기능 ----------
def test_admin_manages_users(make_client, fake_ai):
    user = make_client()
    uid = signup(user, "학생5", "password123")["user"]["id"]
    solve(user)

    assert user.get("/api/admin/users").status_code == 403

    admin = make_client()
    login(admin, *ADMIN)
    rows = {u["username"]: u for u in admin.get("/api/admin/users").json()["users"]}
    assert rows["학생5"]["used_today"] == 1 and rows["학생5"]["effective_limit"] == 3
    assert admin.get("/api/admin/stats").json()["total_users"] == 2

    assert admin.patch(f"/api/admin/users/{uid}", json={"daily_limit": 1}).status_code == 200
    assert solve(user).status_code == 429
    assert admin.patch(f"/api/admin/users/{uid}", json={"use_default_limit": True}).json()["user"]["daily_limit"] is None

    assert admin.patch(f"/api/admin/users/{uid}", json={"new_password": "reset-pass-1"}).status_code == 200
    assert login(user, "학생5", "reset-pass-1").status_code == 200

    assert admin.patch(f"/api/admin/users/{uid}", json={"is_active": False}).status_code == 200
    assert user.get("/api/auth/me").status_code == 401
    assert login(user, "학생5", "reset-pass-1").status_code == 401

    admin_id = admin.get("/api/auth/me").json()["user"]["id"]
    assert admin.patch(f"/api/admin/users/{admin_id}", json={"is_active": False}).status_code == 400
    assert admin.patch(f"/api/admin/users/{uid}", json={"daily_limit": -1}).status_code == 400

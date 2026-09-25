import io
import json

import pytest
from PIL import Image

from tests.conftest import signup

SOLUTION = {
    "problem_title": "도함수-원함수 연계",
    "steps": [
        "g'(x) = f(x) = ln(x^4 + 1) - c",
        r"\frac{1}{3} \times 120 \in \mathbb{N}",
        "mk * e^c = 4 * 2 * 2 = 16",
    ],
    "final_answer": "16",
    "tip": "대칭성 => 높이차",
    "has_diagram": True,
    "diagram": {"diagram_type": "dual_graph", "title": "f, g 연계"},
}


def problem_png(size=(600, 400)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def user_client(client):
    signup(client)
    return client


def render(client, **overrides):
    data = {"solution": json.dumps(SOLUTION), "font": "NanumAmsterdam", "pen": "deepblue", "layout": "margin", "seed": "7"}
    data.update(overrides)
    return client.post("/api/render", files={"image": ("p.png", problem_png(), "image/png")}, data=data)


def test_styles_catalog(client):
    body = client.get("/api/styles").json()
    assert {m["id"] for m in body["solve_modes"]} == {
        "killer_tutor", "standard_concept", "multi_method", "wrong_note", "hint_steps", "report"
    }
    assert {l["id"] for l in body["layouts"]} == {"margin", "postit", "notebook", "report", "cornell"}
    assert any(f["id"] == "NanumAmsterdam" for f in body["fonts"])
    assert all(p["color"].startswith("#") for p in body["pens"])


def test_font_preview_png(client):
    res = client.get("/api/fonts/NanumAmsterdam/preview.png?pen=red")
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert client.get("/api/fonts/nope/preview.png").status_code == 404


@pytest.mark.parametrize("layout", ["margin", "postit", "notebook"])
def test_render_each_layout(user_client, layout):
    res = render(user_client, layout=layout)
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    out = Image.open(io.BytesIO(res.content))
    # 좁은 이미지는 풀이가 잘리지 않도록 캔버스가 넓어지거나 길어져야 합니다
    assert out.width >= 600 and out.height > 400


def test_render_same_seed_is_reproducible(user_client):
    assert render(user_client, seed="42").content == render(user_client, seed="42").content
    assert render(user_client, seed="42").content != render(user_client, seed="43").content


def test_render_rejects_bad_input(user_client):
    client = user_client
    assert render(client, font="nope").status_code == 422
    assert render(client, solution="not json").status_code == 422
    bad = client.post("/api/render", files={"image": ("p.png", b"not an image", "image/png")}, data={"solution": "{}"})
    assert bad.status_code == 400


def test_malicious_diagram_expression_is_not_executed(user_client, tmp_path):
    marker = tmp_path / "pwned"
    evil = dict(SOLUTION, diagram={
        "diagram_type": "coordinate_plane",
        "functions": [{"expr": f"__import__('pathlib').Path('{marker}').touch()"}],
    })
    assert render(user_client, solution=json.dumps(evil)).status_code == 200
    assert not marker.exists()


def test_solve_without_api_key_returns_503(user_client, monkeypatch):
    client = user_client
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    res = client.post("/api/solve", files={"image": ("p.png", problem_png(), "image/png")}, data={"mode": "killer_tutor"})
    assert res.status_code == 503


def test_solve_calls_ai_and_cleans_result(user_client, monkeypatch):
    client = user_client
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    seen = {}

    def fake_solver(image_bytes, mime_type, api_key, solve_style):
        seen.update(mime_type=mime_type, api_key=api_key, solve_style=solve_style)
        return dict(SOLUTION, steps=["x"] * 500, used_model="Gemini Test")

    monkeypatch.setattr("server.main.solve_problem_with_gemini", fake_solver)
    res = client.post("/api/solve", files={"image": ("p.png", problem_png(), "image/png")}, data={"mode": "standard_concept"})
    assert res.status_code == 200
    sol = res.json()["solution"]
    assert seen == {"mime_type": "image/jpeg", "api_key": "test-key", "solve_style": "standard_concept"}
    assert len(sol["steps"]) == 60 and sol["final_answer"] == "16"


def test_solve_ai_failure_returns_502(user_client, monkeypatch):
    client = user_client
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "server.main.solve_problem_with_gemini",
        lambda **_: {"error": True, "error_message": "[gemini-3.8-flash] 503 UNAVAILABLE. high demand"},
    )
    res = client.post("/api/solve", files={"image": ("p.png", problem_png(), "image/png")}, data={"mode": "killer_tutor"})
    assert res.status_code == 502 and "잠시 후 다시" in res.json()["detail"]


def test_serves_web_app(client):
    res = client.get("/")
    assert res.status_code == 200 and "손글씨 해설 노트" in res.text


def test_healthz_checks_database(client, monkeypatch):
    assert client.get("/healthz").json() == {"ok": True}

    from sqlalchemy.exc import OperationalError

    def broken_connect(*a, **kw):
        raise OperationalError("SELECT 1", {}, Exception("db down"))

    monkeypatch.setattr(client.app.state.store.engine, "connect", broken_connect)
    assert client.get("/healthz").status_code == 503


def test_diagram_dropped_when_ai_says_no_diagram():
    from server.main import _clean_solution
    d = {"diagram_type": "geometry"}
    assert _clean_solution({"steps": [], "has_diagram": False, "diagram": d})["diagram"] is None
    assert _clean_solution({"steps": [], "has_diagram": True, "diagram": d})["diagram"] == d

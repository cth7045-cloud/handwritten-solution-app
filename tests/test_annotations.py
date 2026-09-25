import io
import json
import random

import numpy as np
from PIL import Image, ImageDraw

from core.annotation_engine import MAX_ANNOTATIONS, FigureAnnotator, clean_annotations, snap_to_printed_line
from core.handwriting_engine import HandwritingEngine
from tests.conftest import signup

FONT = "수험생 실전 필기체 (갈맷글)"
PEN = "검정색 젤펜"

GOOD = [
    {"type": "label", "point": [500, 300], "text": "3a", "color": "blue"},
    {"type": "note", "point": [100, 700], "text": "cos α = 4/5"},
    {"type": "highlight", "from": [700, 100], "to": [700, 900], "color": "orange"},
    {"type": "line", "from": [200, 100], "to": [700, 500], "dashed": True},
    {"type": "angle", "vertex": [700, 100], "toward1": [700, 900], "toward2": [200, 500], "text": "θ"},
    {"type": "circle", "box": [880, 600, 940, 750]},
    {"type": "strike", "box": [880, 200, 940, 350]},
    {"type": "check", "point": [910, 620]},
]


def test_clean_annotations_keeps_valid_and_drops_bad():
    raw = GOOD + [
        {"type": "unknown", "point": [1, 1]},
        {"type": "label", "point": [1, 1]},                   # 글자 없음
        {"type": "label", "point": "here", "text": "x"},     # 좌표 형식 오류
        {"type": "circle", "box": [500, 500, 400, 600]},      # 뒤집힌 상자
        {"type": "highlight", "from": [1, 2]},                # 끝점 없음
        "not a dict",
    ]
    out = clean_annotations(raw)
    assert [a["type"] for a in out] == [a["type"] for a in GOOD]
    assert out[0]["color"] == "blue" and "color" not in out[1]


def test_clean_annotations_clamps_and_limits():
    out = clean_annotations([{"type": "check", "point": [-50, 5000]}] * (MAX_ANNOTATIONS + 10))
    assert len(out) == MAX_ANNOTATIONS
    assert out[0]["point"] == [0.0, 1000.0]
    assert clean_annotations(None) == [] and clean_annotations({"type": "check"}) == []
    long = clean_annotations([{"type": "note", "point": [1, 1], "text": "가" * 200}])
    assert len(long[0]["text"]) <= 30


def test_highlight_snaps_onto_printed_line():
    img = Image.new("L", (400, 300), 255)
    ImageDraw.Draw(img).line([(50, 150), (350, 150)], fill=0, width=2)
    gray = np.asarray(img, dtype=np.float32)
    (x1, y1), (x2, y2) = snap_to_printed_line(gray, (50, 144), (350, 144), search=10)
    assert abs(y1 - 150) <= 1 and abs(y2 - 150) <= 1
    # 근처에 선이 없으면 그대로 둡니다
    assert snap_to_printed_line(gray, (50, 40), (350, 40), search=10) == ((50, 40), (350, 40))


def test_annotator_draws_every_type_inside_image():
    base = Image.new("RGB", (800, 600), "white")
    random.seed(0)
    out = FigureAnnotator(HandwritingEngine()).annotate(base, clean_annotations(GOOD), FONT, PEN)
    assert out.size == base.size and out.mode == "RGB"
    arr = np.asarray(out).astype(int)
    changed = np.abs(arr - 255).sum(axis=2) > 30
    assert changed.sum() > 2000
    # 빨간 체크/동그라미/빗금이 선택지 줄(아래쪽)에 그려져야 합니다
    red = (arr[..., 0] > 150) & (arr[..., 1] < 100) & (arr[..., 2] < 100)
    assert red[500:, :].sum() > 100
    # 표시가 없으면 원본 그대로
    assert np.array_equal(np.asarray(FigureAnnotator(HandwritingEngine()).annotate(base, [], FONT, PEN)), np.asarray(base))


def _png(size=(600, 400)):
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="PNG")
    return buf.getvalue()


def test_render_marks_toggle(client):
    signup(client)
    sol = {"problem_title": "t", "steps": ["a = 1"], "final_answer": "1", "figure_annotations": GOOD}

    def render(marks, solution=sol):
        res = client.post(
            "/api/render",
            files={"image": ("p.png", _png(), "image/png")},
            data={"solution": json.dumps(solution), "seed": "3", "marks": marks},
        )
        assert res.status_code == 200
        return res.content

    assert render("true") != render("false")
    no_marks = dict(sol, figure_annotations=[])
    assert render("true", no_marks) == render("false", no_marks)


def test_solve_keeps_cleaned_annotations(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "server.main.solve_problem_with_gemini",
        lambda **_: {"steps": ["x"], "final_answer": "1", "figure_annotations": GOOD + [{"type": "bogus"}]},
    )
    signup(client)
    res = client.post("/api/solve", files={"image": ("p.png", _png(), "image/png")}, data={"mode": "killer_tutor"})
    assert res.status_code == 200
    assert len(res.json()["solution"]["figure_annotations"]) == len(GOOD)


def test_label_moves_off_printed_letters():
    from core.annotation_engine import find_clear_spot
    occ = np.zeros((200, 300), dtype=bool)
    occ[90:110, 140:160] = True  # 꼭짓점 글자 'A' 자리
    x, y = find_clear_spot(occ, 140, 90, 20, 20, radius=40)
    assert occ[int(y):int(y) + 20, int(x):int(x) + 20].mean() < 0.05
    assert abs(x - 140) + abs(y - 90) <= 60  # 멀리 가지 않음
    assert find_clear_spot(occ, 10, 10, 20, 20, radius=40) == (10, 10)  # 빈 곳이면 그대로


def test_wide_bogi_box_marks_only_leading_symbol():
    from core.annotation_engine import _symbol_box
    xy = lambda p: (p[1], p[0])  # 1000x1000 이미지
    x1, y1, x2, y2 = _symbol_box(xy, [400, 80, 500, 700], 1000)  # 두 줄짜리 보기 문장 전체
    assert (x2 - x1) < 80 and (y2 - y1) <= 50
    assert _symbol_box(xy, [400, 80, 440, 120], 1000) == (80, 400, 120, 440)  # 작은 상자는 그대로

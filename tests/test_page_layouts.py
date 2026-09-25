import io
import json
import random

import numpy as np
from PIL import Image, ImageDraw

from core.handwriting_engine import HandwritingEngine
from core.overlay_composer import OverlayComposer
from core.page_layouts import A4_H, A4_W, PageComposer, split_cue
from tests.conftest import signup

FONT = "수험생 실전 필기체 (갈맷글)"
PEN = "검정색 젤펜"

SOL = {
    "problem_title": "삼각함수의 극한",
    "problem_summary": "부채꼴 속 삼각형 넓이의 극한",
    "steps": ["[풀이 1] 좌표로 계산", "조건 정리: OH = cos θ", "① 넓이: S(θ) = (1/2) * a * b"],
    "final_answer": "① 1/8",
    "tip": "1 - cos θ ≈ θ²/2",
    "key_concepts": ["삼각함수의 극한"],
    "verification": ["θ = 0.1 대입 ⇒ 0.124"],
}


def _problem():
    img = Image.new("RGB", (700, 500), "white")
    d = ImageDraw.Draw(img)
    for y in range(40, 460, 30):
        d.line([(40, y), (660, y)], fill=0, width=2)
    return img


def _composer():
    return PageComposer(OverlayComposer(HandwritingEngine()))


def test_split_cue():
    assert split_cue("[풀이 1] 대수적 방법") == ("풀이 1", "대수적 방법")
    assert split_cue("조건 정리: g'(x) = 0") == ("조건 정리", "g'(x) = 0")
    assert split_cue("f(x): x + 1") == ("", "f(x): x + 1")  # 한글 없는 머리말은 수식으로 봄
    assert split_cue("x = 3") == ("", "x = 3")


def test_report_is_a4_and_paginates():
    random.seed(0)
    pages = _composer().report_pages(_problem(), SOL, FONT, PEN)
    assert len(pages) == 1 and pages[0].size == (A4_W, A4_H)
    long = dict(SOL, steps=[f"{i}단계: x + {i} = {i + 1}" for i in range(60)])
    pages = _composer().report_pages(_problem(), long, FONT, PEN)
    assert len(pages) >= 2 and all(p.size == (A4_W, A4_H) for p in pages)
    stacked = PageComposer.stack_pages(pages)
    assert stacked.width == A4_W and stacked.height > A4_H * len(pages)


def test_cornell_has_cue_column_and_grows():
    random.seed(0)
    out = _composer().cornell(_problem(), SOL, FONT, PEN)
    assert out.width == A4_W and out.height >= A4_H
    arr = np.asarray(out).astype(int)
    red = (arr[..., 0] > 150) & (arr[..., 1] < 110) & (arr[..., 2] < 110)
    assert red[:, :340].sum() > 200  # 왼쪽 키워드 칸에 빨간 키워드
    long = dict(SOL, steps=[f"{i}단계: x = {i}" for i in range(60)])
    assert _composer().cornell(_problem(), long, FONT, PEN).height > A4_H


def _png():
    buf = io.BytesIO()
    _problem().save(buf, format="PNG")
    return buf.getvalue()


def test_render_report_png_and_pdf(client):
    signup(client)

    def render(**data):
        return client.post(
            "/api/render",
            files={"image": ("p.png", _png(), "image/png")},
            data={"solution": json.dumps(SOL), "layout": "report", **data},
        )

    res = render()
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(res.content)).size == (A4_W, A4_H)
    pdf = render(fmt="pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert render(fmt="gif").status_code == 422
    cornell = client.post(
        "/api/render",
        files={"image": ("p.png", _png(), "image/png")},
        data={"solution": json.dumps(SOL), "layout": "cornell", "fmt": "pdf"},
    )
    assert cornell.status_code == 200 and cornell.content.startswith(b"%PDF")


def test_clean_solution_keeps_report_fields():
    from server.main import _clean_solution
    out = _clean_solution(dict(SOL, key_concepts=["a" * 100, "", None, "b"] + ["c"] * 10, verification="한 줄"))
    assert out["key_concepts"][0] == "a" * 60 and "" not in out["key_concepts"] and len(out["key_concepts"]) <= 6
    assert out["verification"] == ["한 줄"]
    assert _clean_solution({"steps": []})["key_concepts"] == []

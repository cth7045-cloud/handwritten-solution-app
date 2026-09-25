import random

import numpy as np
import pytest
from PIL import Image

from core.handwriting_engine import HandwritingEngine, clean_latex_to_handwriting, format_answer
from core.overlay_composer import OverlayComposer

FONT = "수험생 실전 필기체 (갈맷글)"  # θ, ², ⇒ 글리프가 없는 손글씨 폰트
PEN = "검정색 젤펜"


@pytest.fixture(scope="module")
def engine():
    return HandwritingEngine()


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("costheta, sintheta", "cos θ, sin θ"),
        ("lim_(theta->0+) S(theta)/theta^4 = 1/8", "lim(θ→0+) S(θ)/θ⁴ = 1/8"),
        (r"\frac{1}{2} \times x^{2}", "(1/2) * x²"),
        ("A => B, a <= b, p <=> q, a != b", "A ⇒ B, a ≤ b, p ⇔ q, a ≠ b"),
        (r"\int_0^1 f(x)dx + a_n", "∫₀¹ f(x)dx + aₙ"),
        (r"\angle AOB = 90^\circ", "∠ AOB = 90°"),
        ("e^(ln 2) + (2x)^2", "e^(ln 2) + (2x)²"),
        ("3 * 120 in 자연수", "3 * 120 in 자연수"),
    ],
)
def test_clean_latex_to_handwriting(raw, expected):
    assert clean_latex_to_handwriting(raw) == expected


@pytest.mark.parametrize("raw, expected", [(r"\frac{1}{8}", "1/8"), ("(1/8)", "1/8"), ("(2, 3)", "(2, 3)"), ("16", "16")])
def test_format_answer(raw, expected):
    assert format_answer(raw) == expected


def ink_rows(img: Image.Image):
    alpha = np.array(img.split()[-1])
    rows = np.where(alpha.max(axis=1) > 60)[0]
    return rows.min(), rows.max()


def test_symbols_missing_from_font_are_drawn_not_spelled(engine):
    assert not engine.font_supports_char(FONT, "θ")
    assert engine.sanitize_math_text("θ² ⇒ √2", FONT) == "θ² ⇒ √2"
    # θ 는 'theta' 라는 영어 단어가 아니라 기호 한 글자 폭으로 그려져야 합니다
    assert engine.measure("θ", FONT, 24) < engine.measure("theta", FONT, 24) / 2


def test_words_share_one_baseline(engine):
    """'=' 처럼 키 작은 기호가 위로 떠서 위첨자처럼 보이던 문제."""
    def draw(word):
        canvas = Image.new("RGBA", (200, 80), (255, 255, 255, 0))
        out, _ = engine.draw_handwritten_text(canvas, [word], (10, 10), FONT, 24, PEN, apply_jitter=False)
        return ink_rows(out)

    h_top, h_bottom = draw("H")
    eq_top, eq_bottom = draw("=")
    # '=' 는 H 의 위쪽 절반이 아니라 H 높이의 가운데 부근에 있어야 합니다
    assert eq_top > h_top + (h_bottom - h_top) * 0.2
    assert eq_bottom <= h_bottom + 2


@pytest.mark.parametrize("layout", ["margin", "postit", "notebook"])
def test_answer_circle_drawn_for_latex_answer(engine, monkeypatch, layout):
    """정답이 LaTeX(\\frac{1}{8})로 와도 변환된 '1/8' 을 찾아 동그라미를 쳐야 합니다."""
    comp = OverlayComposer(engine)
    calls = []
    original = engine.draw_answer_circle

    def spy(img, bbox, **kw):
        calls.append(bbox)
        return original(img, bbox, **kw)

    monkeypatch.setattr(engine, "draw_answer_circle", spy)
    base = Image.new("RGB", (900, 300), "white")
    sol = {"problem_title": "t", "steps": ["S(theta) ~ (1/8)theta^4"], "final_answer": r"\frac{1}{8}", "tip": ""}
    random.seed(1)
    compose = {"margin": comp.compose_margin_mode, "postit": comp.compose_postit_mode, "notebook": comp.compose_notebook_extension_mode}
    compose[layout](base, sol, FONT, PEN)

    assert len(calls) == 1
    x1, y1, x2, y2 = calls[0]
    # 레이아웃마다 글자 크기(18~28px)가 달라도 동그라미 폭은 '1/8' 글자 폭과 같아야 합니다
    assert engine.measure("1/8", FONT, 18) <= x2 - x1 <= engine.measure("1/8", FONT, 28)
    assert y2 > y1


def _page_with_margin(w=1400, h=900):
    """위쪽에 인쇄된 문제, 아래쪽 절반은 흰 여백인 문제집 사진 흉내."""
    from PIL import ImageDraw
    img = Image.new("RGB", (w, h), (250, 250, 250))
    d = ImageDraw.Draw(img)
    for y in range(60, 360, 28):
        d.line([(80, y), (w - 80, y)], fill=(30, 30, 30), width=3)
    return img


def test_find_blank_region_detects_empty_margin():
    from core.overlay_composer import find_blank_region
    x, y, bw, bh = find_blank_region(_page_with_margin())
    assert y >= 360 and bh >= 400 and bw >= 1000
    # 여백이 없는(빽빽한) 사진은 None
    busy = Image.effect_noise((800, 600), 80).convert("RGB")
    assert find_blank_region(busy) is None


def test_margin_mode_writes_inside_blank_area_without_extending():
    base = _page_with_margin()
    sol = {
        "problem_title": "절댓값 방정식",
        "steps": [f"{i}단계: x + {i} = {i + 2}" for i in range(1, 9)],
        "final_answer": "2",
        "tip": "구간을 나눠라",
    }
    random.seed(0)
    out = OverlayComposer(HandwritingEngine()).compose_margin_mode(base, sol, "수험생 실전 필기체 (갈맷글)", "검정색 젤펜")
    assert out.size == base.size  # 빈 종이를 덧붙이지 않음
    diff = np.abs(np.asarray(out).astype(int) - np.asarray(base).astype(int)).sum(axis=2) > 40
    assert diff[:360].sum() == 0  # 인쇄된 문제 부분은 건드리지 않음
    assert diff[400:].sum() > 1000  # 여백에 풀이가 적힘

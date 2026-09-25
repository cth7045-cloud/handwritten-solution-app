"""
문제에 들어 있는 그림 위에 강사가 펜으로 표시하듯 풀이를 그려 넣는 엔진.

AI가 이미지 좌표(0~1000 정규화, [y, x] 순서)로 알려준 표시를 원본 사진 위에 그립니다.
  label     : 변 옆에 길이·값 적기 ("3a", "√6")
  note      : 그림 옆 여백에 짧은 메모
  highlight : 그림 속 기존 선분을 형광펜/색연필로 강조 (인쇄된 선에 자동으로 맞춤)
  line      : 보조선 새로 긋기 (점선 가능)
  angle     : 각 표시 (호 + θ 같은 글자)
  circle    : 보기·값에 동그라미
  strike    : 틀린 보기에 빗금
  check     : 정답 선택지 번호 위에 ✓
"""
import math
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw

from .handwriting_engine import PEN_STYLES, HandwritingEngine

Color = Tuple[int, int, int, int]

ANNOTATION_TYPES = ("label", "note", "highlight", "line", "angle", "circle", "strike", "check")
ANNOTATION_COLORS: Dict[str, Tuple[int, int, int]] = {
    "red": (220, 38, 38),
    "blue": (29, 78, 216),
    "orange": (245, 130, 20),
    "green": (22, 140, 60),
}
MAX_ANNOTATIONS = 24
MAX_TEXT = 30


# ---------- AI 응답 정리 ----------
def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return min(1000.0, max(0.0, f))


def _point(v) -> Optional[List[float]]:
    if isinstance(v, (list, tuple)) and len(v) == 2:
        p = [_num(v[0]), _num(v[1])]
        if None not in p:
            return p
    return None


def _box(v) -> Optional[List[float]]:
    if isinstance(v, (list, tuple)) and len(v) == 4:
        b = [_num(x) for x in v]
        if None not in b and b[2] > b[0] and b[3] > b[1]:
            return b
    return None


def clean_annotations(raw: Any) -> List[Dict[str, Any]]:
    """AI가 준 figure_annotations 에서 올바른 항목만 골라 안전한 형태로 돌려줍니다."""
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for a in raw[:MAX_ANNOTATIONS]:
        if not isinstance(a, dict) or a.get("type") not in ANNOTATION_TYPES:
            continue
        t = a["type"]
        item: Dict[str, Any] = {"type": t}
        color = a.get("color")
        if color in ANNOTATION_COLORS:
            item["color"] = color
        if t in ("label", "note"):
            p, text = _point(a.get("point")), str(a.get("text") or "").strip()[:MAX_TEXT]
            if not p or not text:
                continue
            item.update(point=p, text=text)
        elif t in ("highlight", "line"):
            p1, p2 = _point(a.get("from")), _point(a.get("to"))
            if not p1 or not p2:
                continue
            item.update({"from": p1, "to": p2})
            if t == "line":
                item["dashed"] = bool(a.get("dashed"))
        elif t == "angle":
            v, p1, p2 = _point(a.get("vertex")), _point(a.get("toward1")), _point(a.get("toward2"))
            if not v or not p1 or not p2:
                continue
            item.update(vertex=v, toward1=p1, toward2=p2, text=str(a.get("text") or "").strip()[:8])
        elif t in ("circle", "strike"):
            b = _box(a.get("box"))
            if not b:
                continue
            item["box"] = b
        elif t == "check":
            p = _point(a.get("point"))
            if not p:
                continue
            item["point"] = p
        out.append(item)
    return out


# ---------- 그리기 ----------
class FigureAnnotator:
    def __init__(self, engine: HandwritingEngine):
        self.engine = engine

    def annotate(self, img: Image.Image, annotations: Sequence[Dict[str, Any]], font_name: str, pen_style: str) -> Image.Image:
        """annotations(clean_annotations 결과)를 그림 위에 그린 새 이미지를 돌려줍니다."""
        base = img.convert("RGBA")
        if not annotations:
            return base.convert("RGB")
        w, h = base.size
        s = min(w, h)
        pen = PEN_STYLES.get(pen_style, list(PEN_STYLES.values())[0])["color"]
        gray = np.asarray(img.convert("L"), dtype=np.float32)

        def xy(p: Sequence[float]) -> Tuple[float, float]:
            # AI 좌표는 [y, x] 순서, 0~1000 정규화
            return p[1] / 1000 * w, p[0] / 1000 * h

        def color_of(a: Dict[str, Any], default: Color) -> Color:
            c = ANNOTATION_COLORS.get(a.get("color", ""))
            return (*c, 235) if c else default

        stroke = max(2, round(s * 0.004))
        font_size = int(min(60, max(20, s * 0.052)))
        red = (*ANNOTATION_COLORS["red"], 235)

        # 형광펜 강조는 반투명이라 먼저 칠하고, 그 위에 펜 표시를 올립니다
        marker = Image.new("RGBA", base.size, (0, 0, 0, 0))
        mdraw = ImageDraw.Draw(marker)
        for a in annotations:
            if a["type"] == "highlight":
                p1, p2 = snap_to_printed_line(gray, xy(a["from"]), xy(a["to"]), search=max(3, round(s * 0.015)))
                c = ANNOTATION_COLORS.get(a.get("color", ""), ANNOTATION_COLORS["orange"])
                _wobbly_line(mdraw, p1, p2, (*c, 120), width=max(6, round(s * 0.014)), wobble=0.6)
        base.alpha_composite(marker)

        ink = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(ink)
        # (종류, 글자, 픽셀 위치, 색)
        texts: List[Tuple[str, str, Tuple[float, float], Color]] = []
        for a in annotations:
            t = a["type"]
            if t == "line":
                _wobbly_line(draw, xy(a["from"]), xy(a["to"]), color_of(a, pen), width=stroke, dashed=a.get("dashed", False))
            elif t == "angle":
                self._draw_angle(draw, a, xy, color_of(a, pen), stroke, s, texts)
            elif t == "circle":
                x1, y1, x2, y2 = _symbol_box(xy, a["box"], s)
                _hand_ellipse(draw, (x1, y1, x2, y2), color_of(a, red), stroke, pad=max(3, s * 0.008))
            elif t == "strike":
                x1, y1, x2, y2 = _symbol_box(xy, a["box"], s)
                ext = (x2 - x1) * 0.15
                _wobbly_line(draw, (x1 - ext, y2 + ext), (x2 + ext, y1 - ext), color_of(a, red), width=stroke + 1)
            elif t == "check":
                self._draw_check(draw, xy(a["point"]), color_of(a, red), stroke + 1, s)
            elif t in ("label", "note"):
                texts.append((t, a["text"], xy(a["point"]), color_of(a, pen)))
        base.alpha_composite(ink)

        # 글자는 손글씨 엔진으로 (흔들림·기울기·필압).
        # 인쇄된 글자·선이나 이미 쓴 표시 위에 겹치지 않도록 잉크가 있는 곳을 기억해 둡니다.
        occupied = np.asarray(base.convert("L")) < 170
        for kind, text, pos, color in texts:
            base = self._draw_text(base, kind, text, pos, color, font_size, font_name, pen_style, occupied)
        return base.convert("RGB")

    def _draw_text(self, base: Image.Image, kind: str, text: str, pos: Tuple[float, float], color: Color,
                   font_size: int, font_name: str, pen_style: str, occupied: np.ndarray) -> Image.Image:
        w, h = base.size
        x, y = pos
        size = font_size if kind == "label" else int(font_size * 0.85)
        max_w = w * 0.45 if kind == "note" else w * 0.6
        lines = self.engine.wrap_text(text, font_name, size, int(max_w))
        text_w = max((self.engine.measure(l, font_name, size) for l in lines), default=0)
        line_h = size + int(size * 0.3)
        if kind == "label":
            # 라벨은 지정한 점이 글자 가운데에 오도록
            x, y = x - text_w / 2, y - line_h * len(lines) / 2
        box_w, box_h = int(text_w) + 4, line_h * len(lines)
        x, y = find_clear_spot(occupied, x, y, box_w, box_h, radius=int(line_h * 1.2))
        # 그림 밖으로 나가지 않게
        x = min(max(4, x), max(4, w - text_w - 6))
        y = min(max(4, y), max(4, h - line_h * len(lines) - 4))
        occupied[int(y):int(y + box_h), int(x):int(x + box_w)] = True  # 다음 글자는 이 자리를 피합니다
        out, _ = self.engine.draw_handwritten_text(
            base, lines, (int(x), int(y)), font_name, size, pen_style,
            line_spacing=int(size * 0.3), apply_jitter=True, color=color,
        )
        return out

    def _draw_angle(self, draw: ImageDraw.ImageDraw, a: Dict[str, Any], xy, color: Color, stroke: int, s: int, texts):
        vx, vy = xy(a["vertex"])
        (x1, y1), (x2, y2) = xy(a["toward1"]), xy(a["toward2"])
        t1, t2 = math.atan2(y1 - vy, x1 - vx), math.atan2(y2 - vy, x2 - vx)
        # 두 방향 사이의 작은 쪽 각으로 호를 그립니다
        diff = (t2 - t1 + math.pi) % (2 * math.pi) - math.pi
        r = s * 0.045
        steps = max(6, int(abs(diff) * 12))
        pts = []
        for i in range(steps + 1):
            t = t1 + diff * i / steps
            rr = r + random.uniform(-0.6, 0.6)
            pts.append((vx + rr * math.cos(t), vy + rr * math.sin(t)))
        draw.line(pts, fill=color, width=stroke, joint="curve")
        if a.get("text"):
            # 각의 이등분 방향, 호 바깥쪽에 글자
            mid = t1 + diff / 2
            texts.append(("label", a["text"], (vx + r * 1.75 * math.cos(mid), vy + r * 1.75 * math.sin(mid)), color))

    @staticmethod
    def _draw_check(draw: ImageDraw.ImageDraw, p: Tuple[float, float], color: Color, width: int, s: int):
        x, y = p
        k = s * 0.028
        pts = [(x - k, y - k * 0.05), (x - k * 0.25, y + k * 0.75), (x + k * 1.1, y - k * 1.1)]
        pts = [(px + random.uniform(-1, 1), py + random.uniform(-1, 1)) for px, py in pts]
        draw.line(pts, fill=color, width=width, joint="curve")


def _symbol_box(xy, box: Sequence[float], s: int) -> Tuple[float, float, float, float]:
    """circle/strike 상자를 픽셀로 바꿉니다. AI가 보기 문장 전체처럼 가로로 긴 상자를 주면
    강사가 하듯 맨 앞 기호(ㄱ, ㄴ, ㄷ / ①~⑤) 부분만 표시하도록 왼쪽 정사각형 영역으로 줄입니다."""
    x1, y1 = xy([box[0], box[1]])
    x2, y2 = xy([box[2], box[3]])
    h = y2 - y1
    if x2 - x1 > 3 * h:
        # 여러 줄짜리 보기도 기호는 첫 줄 맨 앞에 있으므로 한 줄 높이만큼만
        sym = min(h, s * 0.05)
        x2, y2 = x1 + sym * 1.3, y1 + sym
    return x1, y1, x2, y2


def find_clear_spot(occupied: np.ndarray, x: float, y: float, box_w: int, box_h: int,
                    radius: int) -> Tuple[float, float]:
    """(x, y)에 box_w x box_h 글자 상자를 놓을 때 잉크와 겹치면, radius 안에서 가장 덜 겹치는 가까운 자리를 찾습니다.
    AI가 준 좌표가 꼭짓점 글자(A, E)나 선 바로 위를 가리켜도 글자가 겹치지 않게 합니다."""
    h, w = occupied.shape
    if box_w <= 0 or box_h <= 0:
        return x, y
    integral = np.pad(occupied.astype(np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))

    def overlap(cx: float, cy: float) -> float:
        x0, y0 = int(min(max(0, cx), w - 1)), int(min(max(0, cy), h - 1))
        x1, y1 = min(w, x0 + box_w), min(h, y0 + box_h)
        if x1 <= x0 or y1 <= y0:
            return 1.0
        ink = integral[y1, x1] - integral[y0, x1] - integral[y1, x0] + integral[y0, x0]
        return ink / (box_w * box_h)

    if overlap(x, y) < 0.01:
        return x, y
    step = max(3, box_h // 4)
    best = (overlap(x, y), 0.0, x, y)
    for dy in range(-radius, radius + 1, step):
        for dx in range(-radius, radius + 1, step):
            d = (dx * dx + dy * dy) ** 0.5
            if d > radius:
                continue
            # 겹침이 적을수록, 원래 자리에 가까울수록 좋음. 멀리 옮기면 엉뚱한 선분의 라벨처럼
            # 보이므로 거리 벌점을 제곱으로 크게 줍니다 (꼭 필요한 만큼만 비켜 섬)
            cost = overlap(x + dx, y + dy) + 0.08 * (d / radius) ** 2
            if cost < best[0] + 0.08 * (best[1] / radius) ** 2:
                best = (overlap(x + dx, y + dy), d, x + dx, y + dy)
    return best[2], best[3]


def snap_to_printed_line(gray: np.ndarray, p1: Tuple[float, float], p2: Tuple[float, float],
                         search: int = 8) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """AI가 준 선분 위치가 조금 어긋나 있으면, 가까운 인쇄된 선 위로 평행 이동해 맞춥니다."""
    (x1, y1), (x2, y2) = p1, p2
    length = math.hypot(x2 - x1, y2 - y1)
    if length < 5:
        return p1, p2
    nx, ny = -(y2 - y1) / length, (x2 - x1) / length
    ts = np.linspace(0.15, 0.85, 40)  # 끝점 근처(꼭짓점 글자 등)는 빼고 가운데 부분만 봅니다
    h, w = gray.shape

    def darkness(d: float) -> float:
        xs = np.clip((x1 + (x2 - x1) * ts + nx * d).round().astype(int), 0, w - 1)
        ys = np.clip((y1 + (y2 - y1) * ts + ny * d).round().astype(int), 0, h - 1)
        return float((255 - gray[ys, xs]).mean())

    base = darkness(0)
    best_d, best = 0, base
    for d in range(-search, search + 1):
        v = darkness(d)
        if v > best:
            best_d, best = d, v
    # 확실히 더 진한 선이 있을 때만 옮깁니다
    if best_d != 0 and best > max(base * 1.5, 60):
        return (x1 + nx * best_d, y1 + ny * best_d), (x2 + nx * best_d, y2 + ny * best_d)
    return p1, p2


def _wobbly_line(draw: ImageDraw.ImageDraw, p1, p2, color: Color, width: int, wobble: float = 0.8, dashed: bool = False):
    (x1, y1), (x2, y2) = p1, p2
    length = math.hypot(x2 - x1, y2 - y1)
    if length < 1:
        return
    steps = max(2, int(length / 10))
    nx, ny = -(y2 - y1) / length, (x2 - x1) / length
    pts = []
    for i in range(steps + 1):
        t = i / steps
        j = math.sin(math.pi * t) * random.uniform(-wobble, wobble)
        pts.append((x1 + (x2 - x1) * t + nx * j, y1 + (y2 - y1) * t + ny * j))
    if not dashed:
        draw.line(pts, fill=color, width=width, joint="curve")
        return
    for i in range(0, len(pts) - 1, 2):
        draw.line([pts[i], pts[i + 1]], fill=color, width=width)


def _hand_ellipse(draw: ImageDraw.ImageDraw, box, color: Color, width: int, pad: float):
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    rx, ry = (x2 - x1) / 2 + pad, (y2 - y1) / 2 + pad
    start = random.uniform(-40, -10)
    total = random.uniform(375, 395)
    pts = []
    for i in range(49):
        t = math.radians(start + total * i / 48)
        j = random.uniform(-0.8, 0.8)
        pts.append((cx + (rx + j) * math.cos(t), cy + (ry + j) * math.sin(t)))
    draw.line(pts, fill=color, width=width, joint="curve")

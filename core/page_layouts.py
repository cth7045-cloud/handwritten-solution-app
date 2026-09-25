"""
종이 한 장을 새로 채우는 필기 방식들.

- A4 레포트: 괘선 레포트 용지(A4, 150dpi)에 제목 → 문제 → 핵심 개념 → 풀이 → 검산 → 결론 순서로
  보고서처럼 정리합니다. 한 장을 넘으면 다음 장으로 이어 씁니다.
- 코넬노트: 왼쪽 키워드 칸, 오른쪽 필기 칸, 아래 요약 칸으로 나눈 코넬식 정리 노트.

글자는 모두 괘선(줄) 위에 기준선을 맞춰 씁니다. 한 페이지의 같은 종류 줄은 빈 줄을 끼워
한 번에 그려서(draw_handwritten_text 1회) 긴 풀이도 빠르게 렌더링합니다.
"""
import math
import random
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from .handwriting_engine import PEN_STYLES, HandwritingEngine, format_answer

# A4 (210 x 297mm) 를 150dpi 로
A4_W, A4_H = 1240, 1754
A4_DPI = 150

PAPER = (254, 254, 251)
RULE = (206, 216, 231)
MARGIN_RED = (238, 165, 165)
HIGHLIGHT = (255, 226, 84, 115)
SUBHEAD = (205, 45, 45, 235)  # [풀이 1], [힌트 2] 같은 소제목은 빨간 펜으로

_BRACKET_HEAD = re.compile(r"^\s*\[([^\]]{1,14})\]\s*(.*)$")
_COLON_HEAD = re.compile(r"^\s*([^:=]{1,28}?)\s*:\s+(.+)$")
_HANGUL = re.compile(r"[가-힣]")


def today_text() -> str:
    d = datetime.now(ZoneInfo("Asia/Seoul"))
    return f"{d.year}. {d.month}. {d.day}."


def is_subhead(line: str) -> bool:
    return bool(_BRACKET_HEAD.match(line))


def split_cue(step: str) -> Tuple[str, str]:
    """코넬노트용: "[풀이 1] 대수적 방법" / "조건 정리: g'(x) = 0" 을 (키워드, 내용)으로 나눕니다.
    키워드가 없으면 ("", 원문)."""
    m = _BRACKET_HEAD.match(step)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = _COLON_HEAD.match(step)
    # 한글이 들어 있는 짧은 머리말만 키워드로 봅니다 (비율 1:2, f(x): ... 같은 수식은 제외)
    if m and _HANGUL.search(m.group(1)):
        return m.group(1).strip(), m.group(2).strip()
    return "", step


def _pen_color(pen_style: str) -> Tuple[int, int, int, int]:
    return PEN_STYLES.get(pen_style, list(PEN_STYLES.values())[0])["color"]


def _taped_photo(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    """문제 사진을 종이에 붙인 것처럼: 얇은 테두리, 그림자, 위쪽 모서리에 반투명 테이프."""
    photo = img.convert("RGB")
    scale = min(1.0, max_w / photo.width, max_h / photo.height)
    if scale < 1.0:
        photo = photo.resize((max(1, int(photo.width * scale)), max(1, int(photo.height * scale))), Image.LANCZOS)
    pw, ph = photo.size
    m = 14
    out = Image.new("RGBA", (pw + 2 * m, ph + 2 * m), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    d.rectangle([m + 3, m + 4, m + pw + 3, m + ph + 4], fill=(0, 0, 0, 28))  # 그림자
    out.paste(photo, (m, m))
    d.rectangle([m, m, m + pw - 1, m + ph - 1], outline=(190, 190, 190, 255), width=1)
    for cx in (m + 18, m + pw - 18):
        tape = Image.new("RGBA", (92, 26), (238, 232, 196, 165))
        tape = tape.rotate(random.uniform(-14, 14) + (20 if cx < pw / 2 else -20), expand=True, resample=Image.BICUBIC)
        out.alpha_composite(tape, (max(0, int(cx - tape.width / 2)), max(0, m - tape.height // 2)))
    return out


class _RuledWriter:
    """괘선 위에 줄 단위로 글씨를 쓰는 도우미."""

    def __init__(self, engine: HandwritingEngine, font_name: str, pen_style: str, row_h: int):
        self.engine = engine
        self.font_name = font_name
        self.pen_style = pen_style
        self.row_h = row_h

    def write(self, img: Image.Image, rows: List[str], x: int, top: int, size: int,
              color=None) -> Image.Image:
        """rows[i] 를 i번째 줄(괘선)에 씁니다. 빈 문자열이면 그 줄은 건너뜁니다."""
        if not any(r.strip() for r in rows):
            return img
        cap = self.engine.cap_height(self.font_name, size)
        start = (x, top + self.row_h - 10 - cap)
        img, _ = self.engine.draw_handwritten_text(
            img, rows, start, self.font_name, size, self.pen_style, line_spacing=self.row_h - size, color=color
        )
        return img

    def highlight(self, img: Image.Image, rows: List[str], x: int, top: int, size: int) -> Image.Image:
        """제목 줄 아래쪽 절반에 형광펜을 긋습니다."""
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        cap = self.engine.cap_height(self.font_name, size)
        for i, r in enumerate(rows):
            if not r.strip():
                continue
            w = self.engine.measure(r, self.font_name, size)
            base = top + (i + 1) * self.row_h - 10
            y1 = base - cap * 0.45 + random.uniform(-2, 2)
            d.polygon(
                [(x - 6, y1 + random.uniform(-2, 2)), (x + w + 8, y1 + random.uniform(-2, 2)),
                 (x + w + 6, base + 5), (x - 4, base + 5)],
                fill=HIGHLIGHT,
            )
        img = img.convert("RGBA") if img.mode != "RGBA" else img
        img.alpha_composite(overlay)
        return img


def _ruled_paper(w: int, h: int, top: int, bottom: int, row_h: int, margin_x: Optional[int]) -> Image.Image:
    page = Image.new("RGBA", (w, h), PAPER + (255,))
    d = ImageDraw.Draw(page)
    y = top + row_h
    while y <= bottom:
        d.line([(60, y), (w - 60, y)], fill=RULE, width=1)
        y += row_h
    if margin_x is not None:
        d.line([(margin_x, 40), (margin_x, h - 40)], fill=MARGIN_RED, width=2)
    return page


class PageComposer:
    """A4 레포트와 코넬노트를 만듭니다. overlay 는 정답 동그라미/다이어그램을 재사용하기 위한 OverlayComposer."""

    def __init__(self, overlay):
        self.overlay = overlay
        self.engine: HandwritingEngine = overlay.engine

    def _diagram(self, solution: Dict[str, Any], font_name: str, pen_style: str, max_w: int) -> Optional[Image.Image]:
        data = solution.get("diagram")
        if not isinstance(data, dict):
            return None
        try:
            return self.overlay.diagram_engine.render_diagram(data, font_name, pen_style, max_width=max_w)
        except Exception as e:
            print(f"[!] 다이어그램 렌더링 오류: {e}")
            return None

    # ------------------------------------------------------------------ A4 레포트
    REPORT_ROW = 50
    REPORT_SIZE = 30
    REPORT_LEFT = 130
    REPORT_RIGHT = 100
    REPORT_TOP = 110
    REPORT_BOTTOM = A4_H - 120

    def report_pages(self, base_img: Image.Image, solution: Dict[str, Any], font_name: str, pen_style: str) -> List[Image.Image]:
        eng = self.engine
        size, row_h = self.REPORT_SIZE, self.REPORT_ROW
        head_size = size + 4
        body_w = A4_W - self.REPORT_LEFT - self.REPORT_RIGHT
        wrap = lambda t, s=size, w=body_w: eng.wrap_text(t, font_name, s, w)  # noqa: E731

        # 1) 내용을 블록으로: ("head", 글) / ("text", 줄들, 종류) / ("image", 그림, 테이프여부) / ("gap",)
        blocks: List[tuple] = []
        n = 0
        numerals = "ⅠⅡⅢⅣⅤⅥ"

        def section(title: str):
            nonlocal n
            blocks.append(("head", f"{numerals[n]}. {title}"))
            n += 1

        section("문제")
        blocks.append(("image", _taped_photo(base_img, body_w - 40, 620), True))
        summary = solution.get("problem_summary", "")
        if summary:
            blocks.append(("text", wrap(f"요약: {summary}"), "body"))

        concepts = [c for c in solution.get("key_concepts", []) if c]
        if concepts:
            section("핵심 개념")
            for c in concepts:
                blocks.append(("text", wrap(f"• {c}"), "body"))

        section("풀이 과정")
        for step in solution.get("steps", []):
            blocks.append(("text", wrap(step), "sub" if is_subhead(step) else "body"))
        diag = self._diagram(solution, font_name, pen_style, min(520, body_w))
        if diag is not None:
            blocks.append(("image", diag, False))

        checks = [c for c in solution.get("verification", []) if c]
        if checks:
            section("검산")
            for c in checks:
                blocks.append(("text", wrap(c), "body"))

        ans = format_answer(solution.get("final_answer", ""))
        tip = solution.get("tip", "")
        if ans or tip:
            section("결론")
            if ans:
                blocks.append(("text", wrap(f"∴ 정답: {ans}"), "answer"))
            if tip:
                blocks.append(("text", wrap(f"★ 정리: {tip}"), "body"))

        # 2) 제목 머리글 (첫 장)
        title = solution.get("problem_title", "") or "문제 풀이 보고서"
        title_size = 46
        while title_size > 32 and eng.measure(title, font_name, title_size) > body_w:
            title_size -= 2
        title_lines = eng.wrap_text(title, font_name, title_size, body_w)[:2]
        first_top = 80 + len(title_lines) * (title_size + 22) + 70

        # 3) 페이지 나누기: 각 페이지 = {rows: {행: (글, 종류)}, images: [(행, 행수, 그림)]}
        pages: List[Dict[str, Any]] = []

        def new_page():
            top = first_top if not pages else self.REPORT_TOP
            pages.append({"top": top, "rows": {}, "images": [], "cap": (self.REPORT_BOTTOM - top) // row_h, "used": 0})
            return pages[-1]

        page = new_page()
        for blk in blocks:
            kind = blk[0]
            if kind == "head":
                if page["used"] > 0:
                    page["used"] += 1  # 제목 앞 한 줄 띄우기
                if page["cap"] - page["used"] < 2:  # 제목만 덩그러니 남지 않게
                    page = new_page()
                page["rows"][page["used"]] = (blk[1], "head")
                page["used"] += 1
            elif kind == "text":
                for line in blk[1]:
                    if page["used"] >= page["cap"]:
                        page = new_page()
                    if not line.strip() and page["used"] == 0:
                        continue
                    page["rows"][page["used"]] = (line, blk[2])
                    page["used"] += 1
            elif kind == "image":
                im = blk[1]
                max_rows = (self.REPORT_BOTTOM - self.REPORT_TOP) // row_h
                need = math.ceil((im.height + 16) / row_h)
                if need > max_rows:  # 한 장보다 크면 줄여서
                    s = (max_rows * row_h - 16) / im.height
                    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
                    need = max_rows
                if page["cap"] - page["used"] < need:
                    page = new_page()
                page["images"].append((page["used"], need, im))
                page["used"] += need

        # 4) 그리기
        writer = _RuledWriter(eng, font_name, pen_style, row_h)
        x = self.REPORT_LEFT
        out: List[Image.Image] = []
        for pi, pg in enumerate(pages):
            top = pg["top"]
            img = _ruled_paper(A4_W, A4_H, top, self.REPORT_BOTTOM, row_h, self.REPORT_LEFT - 26)
            if pi == 0:
                img = self._report_header(img, title_lines, title_size, font_name, pen_style, first_top)
            # 그림 자리에는 괘선을 지우고 붙입니다
            for r, need, im in pg["images"]:
                y = top + r * row_h + (need * row_h - im.height) // 2
                ix = x + (A4_W - self.REPORT_LEFT - self.REPORT_RIGHT - im.width) // 2
                img.alpha_composite(im, (int(ix), int(max(top, y))))

            total = max(pg["rows"], default=-1) + 1
            groups: Dict[str, List[str]] = {k: [""] * total for k in ("head", "body", "sub", "answer")}
            for r, (text, kind) in pg["rows"].items():
                groups[kind][r] = text
            img = writer.highlight(img, groups["head"], x, top, head_size)
            img = writer.write(img, groups["head"], x, top, head_size)
            img = writer.write(img, groups["body"], x, top, size)
            img = writer.write(img, groups["sub"], x, top, size, color=SUBHEAD)
            img = writer.write(img, groups["answer"], x, top, size)
            if any(groups["answer"]):
                cap = eng.cap_height(font_name, size)
                img = self.overlay._draw_ans_circle_if_exists(
                    img, groups["answer"], ans, (x, top + row_h - 10 - cap), font_name, size, row_h - size, pen_style
                )
            self._page_number(img, pi + 1, len(pages))
            out.append(img.convert("RGB"))
        return out

    def _report_header(self, img, title_lines, title_size, font_name, pen_style, first_top):
        eng = self.engine
        y = 80
        for line in title_lines:
            w = eng.measure(line, font_name, title_size)
            img, _ = eng.draw_handwritten_text(img, [line], (int((A4_W - w) / 2), y), font_name, title_size, pen_style)
            y += title_size + 22
        date = f"날짜: {today_text()}"
        dw = eng.measure(date, font_name, 26)
        img, _ = eng.draw_handwritten_text(img, [date], (int(A4_W - self.REPORT_RIGHT - dw), y + 4), font_name, 26, pen_style)
        d = ImageDraw.Draw(img)
        line_y = first_top - 16
        color = _pen_color(pen_style)[:3] + (200,)
        d.line([(self.REPORT_LEFT - 40, line_y), (A4_W - 70, line_y + random.uniform(-2, 2))], fill=color, width=2)
        d.line([(self.REPORT_LEFT - 40, line_y + 6), (A4_W - 70, line_y + 6 + random.uniform(-2, 2))], fill=color, width=1)
        return img

    def _page_number(self, img: Image.Image, no: int, total: int):
        font = self.engine.load_symbol_font(30)
        if font is None or total < 2:
            return
        d = ImageDraw.Draw(img)
        text = f"- {no} / {total} -"
        d.text((A4_W / 2, A4_H - 60), text, font=font, fill=(150, 150, 150, 255), anchor="ms")

    @staticmethod
    def stack_pages(pages: List[Image.Image], gap: int = 28) -> Image.Image:
        """여러 장을 PDF 뷰어처럼 세로로 이어 붙인 한 장의 그림 (화면 미리보기/PNG 저장용)."""
        if len(pages) == 1:
            return pages[0]
        w = max(p.width for p in pages)
        h = sum(p.height for p in pages) + gap * (len(pages) - 1)
        out = Image.new("RGB", (w, h), (222, 226, 232))
        y = 0
        for p in pages:
            out.paste(p, (0, y))
            y += p.height + gap
        return out

    # ------------------------------------------------------------------ 코넬노트
    CORNELL_ROW = 48
    CORNELL_SIZE = 28
    CUE_SIZE = 25
    CUE_X, CUE_W = 70, 270
    DIVIDER_X = 360
    NOTE_X = 385
    NOTE_W = A4_W - 385 - 70

    def cornell(self, base_img: Image.Image, solution: Dict[str, Any], font_name: str, pen_style: str) -> Image.Image:
        eng = self.engine
        size, cue_size, row_h = self.CORNELL_SIZE, self.CUE_SIZE, self.CORNELL_ROW
        note_wrap = lambda t: eng.wrap_text(t, font_name, size, self.NOTE_W)  # noqa: E731
        cue_wrap = lambda t: eng.wrap_text(t, font_name, cue_size, self.CUE_W)  # noqa: E731

        cue: List[str] = []
        note: List[str] = []
        sub: List[str] = []  # 빨간 소제목 줄 (note 칸)
        images: List[Tuple[int, int, Image.Image]] = []

        def add(cue_text: str, note_lines: List[str], note_is_sub: bool = False):
            c = cue_wrap(cue_text) if cue_text else []
            rows = max(len(c), len(note_lines), 1)
            for i in range(rows):
                cue.append(c[i] if i < len(c) else "")
                line = note_lines[i] if i < len(note_lines) else ""
                note.append("" if note_is_sub else line)
                sub.append(line if note_is_sub else "")

        def add_image(cue_text: str, im: Image.Image):
            need = math.ceil((im.height + 12) / row_h)
            images.append((len(note), need, im))
            c = cue_wrap(cue_text) if cue_text else []
            for i in range(need):
                cue.append(c[i] if i < len(c) else "")
                note.append("")
                sub.append("")

        add_image("문제", _taped_photo(base_img, self.NOTE_W - 30, 560))
        add("", [])
        for step in solution.get("steps", []):
            key, body = split_cue(step)
            is_bracket = bool(_BRACKET_HEAD.match(step))
            if is_bracket and body:
                add(key, note_wrap(body), note_is_sub=True)
            elif is_bracket:
                add(key, [])
            else:
                add(key, note_wrap(body))
        diag = self._diagram(solution, font_name, pen_style, min(480, self.NOTE_W))
        if diag is not None:
            add_image("그래프", diag)
        ans = format_answer(solution.get("final_answer", ""))
        if ans:
            add("", [])
            add("결론", note_wrap(f"∴ 정답: {ans}"))

        # 아래 요약 칸
        summary: List[str] = []
        concepts = [c for c in solution.get("key_concepts", []) if c]
        if concepts:
            summary += eng.wrap_text("핵심 개념: " + ", ".join(concepts), font_name, size, A4_W - 2 * self.CUE_X - 150)
        tip = solution.get("tip", "")
        if tip:
            summary += eng.wrap_text(f"★ {tip}", font_name, size, A4_W - 2 * self.CUE_X - 150)
        checks = [c for c in solution.get("verification", []) if c]
        for c in checks[:2]:
            summary += eng.wrap_text(f"검산: {c}", font_name, size, A4_W - 2 * self.CUE_X - 150)
        if not summary and ans:
            summary = [f"정답은 {ans}"]

        title = solution.get("problem_title", "") or "코넬 노트"
        title_size = 40
        while title_size > 28 and eng.measure(title, font_name, title_size) > A4_W - 480:
            title_size -= 2
        title_line = eng.wrap_text(title, font_name, title_size, A4_W - 480)[0]

        top = 170
        body_rows = len(note)
        summary_top = top + (body_rows + 1) * row_h
        height = max(A4_H, summary_top + (len(summary) + 2) * row_h + 60)
        img = _ruled_paper(A4_W, height, top, height - 60, row_h, None)

        d = ImageDraw.Draw(img)
        pen = _pen_color(pen_style)[:3] + (190,)
        d.line([(50, top - 8), (A4_W - 50, top - 8)], fill=pen, width=3)  # 제목 아래 굵은 선
        d.line([(self.DIVIDER_X, top - 8), (self.DIVIDER_X, summary_top)], fill=MARGIN_RED, width=2)  # 키워드 칸 경계
        d.line([(50, summary_top), (A4_W - 50, summary_top)], fill=pen, width=3)  # 요약 칸 경계

        img, _ = eng.draw_handwritten_text(img, [title_line], (self.CUE_X, 70), font_name, title_size, pen_style)
        date = today_text()
        dw = eng.measure(date, font_name, 26)
        img, _ = eng.draw_handwritten_text(img, [date], (int(A4_W - 70 - dw), 92), font_name, 26, pen_style)

        for r, need, im in images:
            y = top + r * row_h + (need * row_h - im.height) // 2
            img.alpha_composite(im, (int(self.NOTE_X + (self.NOTE_W - im.width) // 2), int(max(top, y))))

        writer = _RuledWriter(eng, font_name, pen_style, row_h)
        img = writer.write(img, cue, self.CUE_X, top, cue_size, color=SUBHEAD)
        img = writer.write(img, note, self.NOTE_X, top, size)
        img = writer.write(img, sub, self.NOTE_X, top, size, color=SUBHEAD)
        cap = eng.cap_height(font_name, size)
        img = self.overlay._draw_ans_circle_if_exists(
            img, note, ans, (self.NOTE_X, top + row_h - 10 - cap), font_name, size, row_h - size, pen_style
        )

        # 요약 칸: 왼쪽에 "요약", 오른쪽에 내용
        s_top = summary_top
        img = writer.highlight(img, ["요약"], self.CUE_X, s_top, size + 4)
        img = writer.write(img, ["요약"], self.CUE_X, s_top, size + 4)
        img = writer.write(img, summary, self.CUE_X + 150, s_top, size)
        return img.convert("RGB")

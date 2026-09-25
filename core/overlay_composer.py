"""
다양한 레이아웃(빈 공간 여백 직접 쓰기, 포스트잇 메모지, 모눈노트 확장)으로
문제 본문을 가리지 않고 실제 시험지의 자연스러운 여백에 손글씨 풀이를 합성하는 모듈
이미지가 좁거나 잘려 있는 경우(크롭 스크린샷 등) 지능적으로 캔버스를 확장하여 글씨가 잘리지 않도록 보장합니다.
"""
import random
from typing import Dict, Any, Tuple, Optional, List
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from .handwriting_engine import HandwritingEngine, PEN_STYLES, clean_latex_to_handwriting, format_answer
from .diagram_engine import HandwrittenDiagramEngine

POSTIT_COLORS = {
    "노란색": (255, 250, 195),
    "분홍색": (255, 225, 235),
    "민트색": (220, 250, 235),
    "하늘색": (225, 240, 255),
}

def sample_background_color(base_img: Image.Image) -> Tuple[int, int, int]:
    """이미지 가장자리/여백의 배경색을 스마트하게 추출합니다."""
    rgb = base_img.convert("RGB")
    w, h = rgb.size
    
    # 테두리 픽셀 샘플링
    sample_points = [
        (5, 5), (w - 6, 5), (5, h - 6), (w - 6, h - 6),
        (w // 2, 5), (w // 2, h - 6), (5, h // 2), (w - 6, h // 2)
    ]
    pixels = [rgb.getpixel((max(0, min(w - 1, px)), max(0, min(h - 1, py)))) for px, py in sample_points]
    bright_pixels = [p for p in pixels if sum(p) > 480]
    
    if bright_pixels:
        r = int(sum(p[0] for p in bright_pixels) / len(bright_pixels))
        g = int(sum(p[1] for p in bright_pixels) / len(bright_pixels))
        b = int(sum(p[2] for p in bright_pixels) / len(bright_pixels))
        return (r, g, b)
    return (255, 255, 255)

def detect_content_bounds(base_img: Image.Image) -> Tuple[int, int, int, int]:
    """
    이미지 내 인쇄된 텍스트 및 본문 영역의 경계(min_x, min_y, max_x, max_y)를 정확하게 감지합니다.
    """
    orig_w, orig_h = base_img.size
    sw = 300
    sh = max(50, int(300 * orig_h / orig_w))
    small = base_img.convert("L").resize((sw, sh))
    arr = np.array(small)

    # 텍스트 픽셀 검출 (어두운 글자 영역)
    dark_mask = arr < 175

    text_rows, text_cols = np.where(dark_mask)

    if len(text_rows) > 0:
        max_row = np.max(text_rows)
        min_row = np.min(text_rows)
        max_col = np.max(text_cols)
        min_col = np.min(text_cols)

        real_max_y = int((max_row / sh) * orig_h)
        real_min_y = int((min_row / sh) * orig_h)
        real_max_x = int((max_col / sw) * orig_w)
        real_min_x = int((min_col / sw) * orig_w)
        return real_min_x, real_min_y, real_max_x, real_max_y
    else:
        return int(orig_w * 0.05), int(orig_h * 0.05), int(orig_w * 0.95), int(orig_h * 0.8)

def find_blank_region(base_img: Image.Image) -> Optional[Tuple[int, int, int, int]]:
    """사진 속 '종이 색'으로 비어 있는 가장 큰 직사각형 여백을 찾아 (x, y, w, h)로 돌려줍니다.

    가장 아래쪽 잉크 위치만 보던 방식은 태블릿/휴대폰 화면 캡처처럼 아래에 앱 아이콘·
    내비게이션 바가 있으면 여백이 없다고 판단했습니다. 여기서는 종이 색(가장 흔한 밝은 색)과
    같은 색으로 고르게 비어 있는 칸들만 모아 가장 큰 사각형을 고릅니다. 회색 앱 배경처럼
    종이와 색이 다른 곳은 여백으로 치지 않습니다."""
    gray = np.asarray(base_img.convert("L"), dtype=np.int16)
    h, w = gray.shape
    cell = max(6, round(w / 120))
    rows, cols = h // cell, w // cell
    if rows < 4 or cols < 4:
        return None
    blocks = gray[: rows * cell, : cols * cell].reshape(rows, cell, cols, cell)
    c_min, c_max = blocks.min(axis=(1, 3)), blocks.max(axis=(1, 3))
    c_mean = blocks.mean(axis=(1, 3))

    uniform = (c_max - c_min) < 22
    bright = c_mean[uniform & (c_mean > 170)]
    if bright.size < rows * cols * 0.05:
        return None
    paper = float(np.median(bright[bright >= np.percentile(bright, 60)]))  # 가장 밝은 쪽 무리의 색 = 종이
    free = uniform & (np.abs(c_mean - paper) < 14)

    # 히스토그램 방식의 최대 직사각형
    best = (0, 0, 0, 0, 0)  # area, row_top, col_left, n_rows, n_cols
    heights = np.zeros(cols, dtype=int)
    for r in range(rows):
        heights = np.where(free[r], heights + 1, 0)
        stack: List[int] = []
        for c in range(cols + 1):
            cur = heights[c] if c < cols else 0
            while stack and heights[stack[-1]] >= cur:
                top = stack.pop()
                height = heights[top]
                left = stack[-1] + 1 if stack else 0
                width = c - left
                if height * width > best[0]:
                    best = (height * width, r - height + 1, left, height, width)
            stack.append(c)
    _, r0, c0, nr, nc = best
    # 인쇄된 내용과 너무 붙지 않게 한 칸씩 안쪽으로
    if nr < 3 or nc < 3:
        return None
    x, y = int((c0 + 1) * cell), int((r0 + 1) * cell)
    bw, bh = int((nc - 2) * cell), int((nr - 2) * cell)
    # 좁은 세로 띠(오른쪽 끝 여백 등)에 쓰면 수식이 잘게 끊겨 보기 나쁘므로 충분히 넓을 때만
    if bw < max(300, w * 0.38) or bh < 60:
        return None
    return x, y, bw, bh


class OverlayComposer:
    def __init__(self, engine: HandwritingEngine):
        self.engine = engine
        self.diagram_engine = HandwrittenDiagramEngine(engine)

    def _draw_ans_circle_if_exists(
        self,
        img: Image.Image,
        lines: List[str],
        ans: str,
        start_pos: Tuple[int, int],
        font_name: str,
        font_size: int,
        line_spacing: int,
        pen_style: str
    ) -> Image.Image:
        """최종 정답 텍스트가 위치한 영역을 찾아 자연스러운 손글씨 타원 동그라미를 둘러줍니다."""
        if not ans or not str(ans).strip():
            return img
        # 줄(lines)은 이미 손글씨용으로 변환돼 있으므로 정답도 같은 방식으로 변환한 뒤 찾습니다
        ans_clean = self.engine.sanitize_math_text(clean_latex_to_handwriting(format_answer(ans)), font_name)
        if not ans_clean:
            return img
        target_idx = -1
        for idx, l in enumerate(lines):
            if "정답" in l and ans_clean in l:
                target_idx = idx
                break
        if target_idx == -1:
            return img

        line_y = start_pos[1] + target_idx * (font_size + line_spacing)
        baseline = line_y + self.engine.cap_height(font_name, font_size)
        prefix = lines[target_idx].split(ans_clean, 1)[0]
        prefix_w = self.engine.measure(prefix, font_name, font_size)
        ans_w = self.engine.measure(ans_clean, font_name, font_size)

        x1 = start_pos[0] + prefix_w
        y1 = baseline - self.engine.cap_height(font_name, font_size)
        x2 = x1 + ans_w
        y2 = baseline + font_size * 0.15

        style = PEN_STYLES.get(pen_style, list(PEN_STYLES.values())[0])
        pen_color = style["color"]
        # 정답 바로 앞 공백 폭만큼만 왼쪽으로 나갈 수 있음 (그 이상이면 "정답:" 글자를 덮음)
        left_room = max(1.0, self.engine.measure(" ", font_name, font_size) - 2) if prefix.endswith(" ") else 1.0
        return self.engine.draw_answer_circle(img, bbox=(x1, y1, x2, y2), color=pen_color, width=2, left_room=left_room)

    def _solution_lines(self, solution_data: Dict[str, Any], font_name: str, size: int, wrap_w: int) -> List[str]:
        lines: List[str] = []
        title = solution_data.get("problem_title", "")
        if title:
            lines.extend(self.engine.wrap_text(f"<{title}>", font_name, size, wrap_w))
            lines.append("")
        for step in solution_data.get("steps", []):
            lines.extend(self.engine.wrap_text(step, font_name, size, wrap_w))
        ans = format_answer(solution_data.get("final_answer", ""))
        if ans:
            lines.append("")
            lines.extend(self.engine.wrap_text(f"∴ 정답: {ans}", font_name, size, wrap_w))
        tip = solution_data.get("tip", "")
        if tip:
            lines.append("")
            lines.extend(self.engine.wrap_text(f"★ 핵심 Tip: {tip}", font_name, size, wrap_w))
        return lines

    def _compose_in_blank_region(
        self, base_img: Image.Image, solution_data: Dict[str, Any], font_name: str, pen_style: str
    ) -> Optional[Image.Image]:
        """사진 속 빈 여백에 풀이를 씁니다. 다 들어가지 않으면 남은 줄(과 그래프)을 사진 아래에 이어 씁니다.
        쓸 만한 여백이 없으면 None (기존 방식으로 캔버스를 확장)."""
        region = find_blank_region(base_img)
        if region is None:
            return None
        rx, ry, rw, rh = region
        orig_w, orig_h = base_img.size
        pad = int(rw * 0.04)
        wrap_w = rw - 2 * pad

        # 다 들어가는 가장 큰 글자 크기를 찾고, 안 되면 적당한 크기로 나눠 씁니다
        size_max = max(18, min(30, int(orig_w * 0.022)))
        size_min = max(16, int(orig_w * 0.013))
        chosen = None
        for size in range(size_max, size_min - 1, -1):
            spacing = int(size * 0.45)
            lines = self._solution_lines(solution_data, font_name, size, wrap_w)
            if len(lines) * (size + spacing) <= rh - pad:
                chosen = (size, spacing, lines)
                break
        columns = 1
        if chosen is None and rw >= 700:
            # 여백이 넓으면 사람처럼 두 단으로 나눠 써서 여백 안에 다 넣어 봅니다
            col_w = (rw - 3 * pad) // 2
            for size in range(size_max, size_min - 1, -1):
                spacing = int(size * 0.45)
                lines = self._solution_lines(solution_data, font_name, size, col_w)
                if -(-len(lines) // 2) * (size + spacing) <= rh - pad:
                    chosen, columns, wrap_w = (size, spacing, lines), 2, col_w
                    break
        if chosen is None:
            size = max(size_min, int(size_max * 0.85))
            spacing = int(size * 0.45)
            chosen = (size, spacing, self._solution_lines(solution_data, font_name, size, wrap_w))
        size, spacing, lines = chosen
        line_h = size + spacing
        rows = max(0, (rh - pad) // line_h)
        n_fit = min(len(lines), rows * columns)
        if n_fit < 4:
            return None  # 여백이 너무 작아 몇 줄 못 쓰면 기존 방식이 더 보기 좋음

        diag_img = None
        diagram_data = solution_data.get("diagram")
        if diagram_data and isinstance(diagram_data, dict):
            try:
                diag_img = self.diagram_engine.render_diagram(diagram_data, font_name, pen_style, max_width=min(420, orig_w - 80))
            except Exception as e:
                print(f"[!] 다이어그램 렌더링 오류: {e}")

        head, rest = lines[:n_fit], lines[n_fit:]
        # 여백에서 줄이 끝나면 빈 줄로 시작하지 않게
        while rest and not rest[0].strip():
            rest.pop(0)

        extra_h = 0
        if rest or diag_img is not None:
            extra_h = 40 + len(rest) * line_h + (diag_img.height + 30 if diag_img is not None else 0) + 30
        bg = sample_background_color(base_img)
        canvas = Image.new("RGBA", (orig_w, orig_h + extra_h), bg + (255,))
        canvas.paste(base_img.convert("RGBA"), (0, 0))
        ans = format_answer(solution_data.get("final_answer", ""))

        if columns == 2:
            first, second = head[:rows], head[rows:]
            # 둘째 단이 빈 줄로 시작하지 않게
            while second and not second[0].strip():
                second.pop(0)
            blocks = [(first, (rx + pad, ry + pad // 2)), (second, (rx + 2 * pad + wrap_w, ry + pad // 2))]
        else:
            blocks = [(head, (rx + pad, ry + pad // 2))]
        for block, start in blocks:
            canvas, _ = self.engine.draw_handwritten_text(canvas, block, start, font_name, size, pen_style, line_spacing=spacing)
            canvas = self._draw_ans_circle_if_exists(canvas, block, ans, start, font_name, size, spacing, pen_style)

        if extra_h:
            draw = ImageDraw.Draw(canvas)
            div_y = orig_h + 14
            draw.line([(int(orig_w * 0.05), div_y), (int(orig_w * 0.95), div_y)], fill=(210, 218, 228, 200), width=1)
            y = div_y + 26
            if rest:
                start2 = (rx + pad, y)
                canvas, _ = self.engine.draw_handwritten_text(canvas, rest, start2, font_name, size, pen_style, line_spacing=spacing)
                canvas = self._draw_ans_circle_if_exists(canvas, rest, ans, start2, font_name, size, spacing, pen_style)
                y += len(rest) * line_h + 10
            if diag_img is not None:
                canvas.alpha_composite(diag_img, (max(10, (orig_w - diag_img.width) // 2), int(y)))
        return canvas.convert("RGB")

    def compose_margin_mode(
        self,
        base_img: Image.Image,
        solution_data: Dict[str, Any],
        font_name: str,
        pen_style: str,
        *args,
        **kwargs
    ) -> Image.Image:
        """
        일반 시험지/문제집의 자연스러운 빈 공간에 직접 손글씨를 적은 것처럼 합성합니다.
        문제가 꽉 차있거나 좁게 크롭된 경우(스크린샷 등) 캔버스를 여유롭게 확장하여
        글씨가 삐져나오거나 잘리지 않고 고품질 학습 노트 형태로 완성되도록 보장합니다.
        그래프나 다이어그램이 있을 경우 최적의 위치에 자연스럽게 함께 렌더링합니다.
        """
        # 0. 사진 속 빈 여백이 넉넉하면 그 안에 먼저 쓰고, 모자란 부분만 아래로 이어 씁니다
        in_blank = self._compose_in_blank_region(base_img, solution_data, font_name, pen_style)
        if in_blank is not None:
            return in_blank

        orig_w, orig_h = base_img.size
        min_x, min_y, max_x, max_y = detect_content_bounds(base_img)

        # 1. 캔버스 너비 표준화: 최소 860px을 보장하여 좁은 크롭 스크린샷에서도 수식/풀이가 여유 있게 들어감
        min_comfortable_w = 860
        target_w = max(orig_w, min_comfortable_w)

        # 다이어그램 렌더링 시도
        diag_img = None
        diagram_data = solution_data.get("diagram")
        if diagram_data and (solution_data.get("has_diagram") or isinstance(diagram_data, dict)):
            try:
                diag_max_w = 420 if target_w >= 920 else min(target_w - 110, 420)
                diag_img = self.diagram_engine.render_diagram(diagram_data, font_name, pen_style, max_width=diag_max_w)
            except Exception as e:
                print(f"[!] 다이어그램 렌더링 오류: {e}")
                diag_img = None

        is_side_by_side = (diag_img is not None and target_w >= 920)

        # 폰트 크기 및 행간
        font_size = max(21, min(26, int(target_w * 0.026)))
        line_spacing = int(font_size * 0.45)
        
        # 가로 래핑 최대 너비
        if is_side_by_side:
            max_wrap_w = target_w - diag_img.width - 130
        else:
            max_wrap_w = target_w - 120

        # 풀이 텍스트 라인 구성
        lines_to_draw: List[str] = []
        title = solution_data.get("problem_title", "")
        if title:
            lines_to_draw.extend(self.engine.wrap_text(f"<{title}>", font_name, font_size, max_wrap_w))
            lines_to_draw.append("")
        
        for step in solution_data.get("steps", []):
            lines_to_draw.extend(self.engine.wrap_text(step, font_name, font_size, max_wrap_w))

        ans = format_answer(solution_data.get("final_answer", ""))
        if ans:
            lines_to_draw.append("")
            lines_to_draw.extend(self.engine.wrap_text(f"∴ 정답: {ans}", font_name, font_size, max_wrap_w))

        tip = solution_data.get("tip", "")
        if tip:
            lines_to_draw.append("")
            lines_to_draw.extend(self.engine.wrap_text(f"★ 핵심 Tip: {tip}", font_name, font_size, max_wrap_w))

        # 전체 높이 계산
        text_block_h = len(lines_to_draw) * (font_size + line_spacing)
        if is_side_by_side:
            total_text_h = max(text_block_h, diag_img.height) + 80
        elif diag_img is not None:
            total_text_h = text_block_h + diag_img.height + 100
        else:
            total_text_h = text_block_h + 80

        # 배경색 추출
        bg_rgb = sample_background_color(base_img)

        # 2. 원본 이미지가 이미 넓고(>=860px) 하단 여백이 텍스트를 담기에 충분한지 검사
        bottom_space = max(0, orig_h - max_y - 20)
        if orig_w >= min_comfortable_w and bottom_space >= total_text_h + 40:
            working_img = base_img.convert("RGBA")
            start_x = max(int(orig_w * 0.07), min_x)
            start_y = max_y + 28
        else:
            if orig_w < min_comfortable_w:
                img_x = 55
                img_y = 25
                div_y = img_y + orig_h + 20
                start_x = 55
                start_y = div_y + 35
                total_h = start_y + total_text_h + 60

                working_img = Image.new("RGBA", (target_w, total_h), bg_rgb + (255,))
                working_img.paste(base_img.convert("RGBA"), (img_x, img_y))

                draw = ImageDraw.Draw(working_img)
                draw.rectangle([img_x - 1, img_y - 1, img_x + orig_w, img_y + orig_h], outline=(225, 230, 238, 220), width=1)
                draw.line([(45, div_y), (target_w - 45, div_y)], fill=(215, 222, 232, 220), width=1)
            else:
                new_h = orig_h + total_text_h + 80
                working_img = Image.new("RGBA", (orig_w, new_h), bg_rgb + (255,))
                working_img.paste(base_img.convert("RGBA"), (0, 0))

                draw = ImageDraw.Draw(working_img)
                div_y = orig_h + 16
                draw.line([(int(orig_w * 0.05), div_y), (int(orig_w * 0.95), div_y)], fill=(210, 218, 228, 200), width=1)

                start_x = int(orig_w * 0.07)
                start_y = div_y + 36

        # 손글씨 및 다이어그램 합성 렌더링
        if is_side_by_side:
            result, end_pos = self.engine.draw_handwritten_text(
                base_img=working_img,
                text_lines=lines_to_draw,
                start_pos=(start_x, start_y),
                font_name=font_name,
                font_size=font_size,
                pen_style_name=pen_style,
                line_spacing=line_spacing,
                apply_jitter=True
            )
            diag_x = target_w - diag_img.width - 50
            diag_y = start_y + 8
            result.alpha_composite(diag_img, (diag_x, diag_y))
            result = self._draw_ans_circle_if_exists(
                img=result,
                lines=lines_to_draw,
                ans=ans,
                start_pos=(start_x, start_y),
                font_name=font_name,
                font_size=font_size,
                line_spacing=line_spacing,
                pen_style=pen_style
            )
            return result.convert("RGB")
        elif diag_img is not None:
            title_lines = []
            if title:
                title_lines.extend(self.engine.wrap_text(f"<{title}>", font_name, font_size, max_wrap_w))
                title_lines.append("")
            
            result, end_pos = self.engine.draw_handwritten_text(
                base_img=working_img,
                text_lines=title_lines,
                start_pos=(start_x, start_y),
                font_name=font_name,
                font_size=font_size,
                pen_style_name=pen_style,
                line_spacing=line_spacing,
                apply_jitter=True
            )
            diag_x = max(start_x, (target_w - diag_img.width) // 2)
            diag_y = end_pos[1] + 12
            result.alpha_composite(diag_img, (diag_x, diag_y))
            
            remaining_lines = []
            for step in solution_data.get("steps", []):
                remaining_lines.extend(self.engine.wrap_text(step, font_name, font_size, max_wrap_w))
            if ans:
                remaining_lines.append("")
                remaining_lines.extend(self.engine.wrap_text(f"∴ 정답: {ans}", font_name, font_size, max_wrap_w))
            if tip:
                remaining_lines.append("")
                remaining_lines.extend(self.engine.wrap_text(f"★ 핵심 Tip: {tip}", font_name, font_size, max_wrap_w))
                
            rem_start_y = int(diag_y + diag_img.height + 18)
            result, end_pos = self.engine.draw_handwritten_text(
                base_img=result,
                text_lines=remaining_lines,
                start_pos=(start_x, rem_start_y),
                font_name=font_name,
                font_size=font_size,
                pen_style_name=pen_style,
                line_spacing=line_spacing,
                apply_jitter=True
            )
            result = self._draw_ans_circle_if_exists(
                img=result,
                lines=remaining_lines,
                ans=ans,
                start_pos=(start_x, rem_start_y),
                font_name=font_name,
                font_size=font_size,
                line_spacing=line_spacing,
                pen_style=pen_style
            )
            return result.convert("RGB")
        else:
            result, end_pos = self.engine.draw_handwritten_text(
                base_img=working_img,
                text_lines=lines_to_draw,
                start_pos=(start_x, start_y),
                font_name=font_name,
                font_size=font_size,
                pen_style_name=pen_style,
                line_spacing=line_spacing,
                apply_jitter=True
            )
            result = self._draw_ans_circle_if_exists(
                img=result,
                lines=lines_to_draw,
                ans=ans,
                start_pos=(start_x, start_y),
                font_name=font_name,
                font_size=font_size,
                line_spacing=line_spacing,
                pen_style=pen_style
            )
            return result.convert("RGB")


    def compose_postit_mode(
        self,
        base_img: Image.Image,
        solution_data: Dict[str, Any],
        font_name: str,
        pen_style: str,
        postit_color_name: str = "노란색",
        *args,
        **kwargs
    ) -> Image.Image:
        """
        문제 지문을 가리지 않도록 포스트잇 메모지를 합성합니다.
        문제가 작거나 좁은 경우 캔버스를 여유롭게 확장하여 포스트잇이 잘리는 현상을 100% 방지합니다.
        """
        orig_w, orig_h = base_img.size
        min_x, min_y, max_x, max_y = detect_content_bounds(base_img)

        # 포스트잇 가로 크기: 기본 520px 이상 확보
        postit_w = max(520, min(720, int(orig_w * 0.88)))
        wrap_w = postit_w - 60
        font_size = max(19, min(23, int(postit_w * 0.035)))
        line_spacing = int(font_size * 0.45)

        lines_to_draw: List[str] = []
        title = solution_data.get("problem_title", "풀이 과정")
        if title:
            lines_to_draw.extend(self.engine.wrap_text(f"[풀이] {title}", font_name, font_size, wrap_w))
            lines_to_draw.append("")

        for step in solution_data.get("steps", []):
            lines_to_draw.extend(self.engine.wrap_text(step, font_name, font_size, wrap_w))

        ans = format_answer(solution_data.get("final_answer", ""))
        if ans:
            lines_to_draw.append("")
            lines_to_draw.extend(self.engine.wrap_text(f"정답: {ans}", font_name, font_size, wrap_w))

        tip = solution_data.get("tip", "")
        if tip:
            lines_to_draw.append("")
            lines_to_draw.extend(self.engine.wrap_text(f"Tip: {tip}", font_name, font_size, wrap_w))

        # 다이어그램 렌더링 시도
        diag_img = None
        diagram_data = solution_data.get("diagram")
        if diagram_data and (solution_data.get("has_diagram") or isinstance(diagram_data, dict)):
            try:
                diag_max_w = min(postit_w - 60, 420)
                diag_img = self.diagram_engine.render_diagram(diagram_data, font_name, pen_style, max_width=diag_max_w)
            except Exception as e:
                print(f"[!] 포스트잇 다이어그램 렌더링 오류: {e}")
                diag_img = None

        tape_h = 32
        text_block_h = len(lines_to_draw) * (font_size + line_spacing)
        if diag_img:
            postit_h = max(380, text_block_h + diag_img.height + tape_h + 80)
        else:
            postit_h = max(340, text_block_h + tape_h + 70)

        bg_rgb = POSTIT_COLORS.get(postit_color_name, (255, 250, 195))

        # 포스트잇 생성
        postit = Image.new("RGBA", (postit_w, postit_h), bg_rgb + (255,))
        draw = ImageDraw.Draw(postit)

        # 상단 마스킹 테이프 효과
        darker_color = (max(0, bg_rgb[0] - 20), max(0, bg_rgb[1] - 20), max(0, bg_rgb[2] - 20), 180)
        draw.rectangle([0, 0, postit_w, tape_h], fill=darker_color)

        if diag_img is not None:
            title_lines = []
            if title:
                title_lines.extend(self.engine.wrap_text(f"[풀이] {title}", font_name, font_size, wrap_w))
                title_lines.append("")
            postit_with_text, end_pos = self.engine.draw_handwritten_text(
                base_img=postit,
                text_lines=title_lines,
                start_pos=(30, tape_h + 20),
                font_name=font_name,
                font_size=font_size,
                pen_style_name=pen_style,
                line_spacing=line_spacing,
                apply_jitter=True
            )
            diag_x = max(20, (postit_w - diag_img.width) // 2)
            diag_y = end_pos[1] + 8
            postit_with_text.alpha_composite(diag_img, (int(diag_x), int(diag_y)))
            
            remaining_lines = []
            for step in solution_data.get("steps", []):
                remaining_lines.extend(self.engine.wrap_text(step, font_name, font_size, wrap_w))
            if ans:
                remaining_lines.append("")
                remaining_lines.extend(self.engine.wrap_text(f"정답: {ans}", font_name, font_size, wrap_w))
            if tip:
                remaining_lines.append("")
                remaining_lines.extend(self.engine.wrap_text(f"Tip: {tip}", font_name, font_size, wrap_w))

            rem_pos = (30, int(diag_y + diag_img.height + 15))
            postit_with_text, end_pos = self.engine.draw_handwritten_text(
                base_img=postit_with_text,
                text_lines=remaining_lines,
                start_pos=rem_pos,
                font_name=font_name,
                font_size=font_size,
                pen_style_name=pen_style,
                line_spacing=line_spacing,
                apply_jitter=True
            )
            postit_with_text = self._draw_ans_circle_if_exists(
                img=postit_with_text,
                lines=remaining_lines,
                ans=ans,
                start_pos=rem_pos,
                font_name=font_name,
                font_size=font_size,
                line_spacing=line_spacing,
                pen_style=pen_style
            )
        else:
            base_pos = (30, tape_h + 20)
            postit_with_text, end_pos = self.engine.draw_handwritten_text(
                base_img=postit,
                text_lines=lines_to_draw,
                start_pos=base_pos,
                font_name=font_name,
                font_size=font_size,
                pen_style_name=pen_style,
                line_spacing=line_spacing,
                apply_jitter=True
            )
            postit_with_text = self._draw_ans_circle_if_exists(
                img=postit_with_text,
                lines=lines_to_draw,
                ans=ans,
                start_pos=base_pos,
                font_name=font_name,
                font_size=font_size,
                line_spacing=line_spacing,
                pen_style=pen_style
            )


        # 그림자 및 자연스러운 미세 회전
        angle = random.uniform(-1.0, 1.0)
        pad = 30
        shadow_box = Image.new("RGBA", (postit_w + pad * 2, postit_h + pad * 2), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow_box)
        sdraw.rectangle([pad + 4, pad + 8, pad + postit_w + 4, pad + postit_h + 8], fill=(0, 0, 0, 55))
        shadow_box = shadow_box.filter(ImageFilter.GaussianBlur(10))

        shadow_box.alpha_composite(postit_with_text, (pad, pad))
        rotated_postit = shadow_box.rotate(angle, resample=Image.BICUBIC, expand=True)

        # 캔버스 크기 결정: 캔버스 너비는 최소 (rotated_postit.width + 80) 이상이어야 잘리지 않음!
        target_canvas_w = max(orig_w, rotated_postit.width + 80)
        bg_rgb_base = sample_background_color(base_img)

        # 하단 공간 판별
        bottom_space = max(0, orig_h - max_y - 20)
        if orig_w >= target_canvas_w and bottom_space >= rotated_postit.height + 40:
            result = base_img.convert("RGBA")
            target_x = max(15, (orig_w - rotated_postit.width) // 2)
            target_y = max_y + 20
        else:
            # 캔버스 확장
            if orig_w < target_canvas_w:
                target_canvas_h = orig_h + rotated_postit.height + 70
                result = Image.new("RGBA", (target_canvas_w, target_canvas_h), bg_rgb_base + (255,))
                img_x = (target_canvas_w - orig_w) // 2
                result.paste(base_img.convert("RGBA"), (img_x, 20))
                target_x = (target_canvas_w - rotated_postit.width) // 2
                target_y = orig_h + 40
            else:
                target_canvas_h = orig_h + rotated_postit.height + 60
                result = Image.new("RGBA", (orig_w, target_canvas_h), bg_rgb_base + (255,))
                result.paste(base_img.convert("RGBA"), (0, 0))
                target_x = max(15, (orig_w - rotated_postit.width) // 2)
                target_y = orig_h + 20

        result.alpha_composite(rotated_postit, (int(target_x), int(target_y)))
        return result.convert("RGB")

    def compose_notebook_extension_mode(
        self,
        base_img: Image.Image,
        solution_data: Dict[str, Any],
        font_name: str,
        pen_style: str,
        *args,
        **kwargs
    ) -> Image.Image:
        """
        원본 이미지 우측에 모눈종이(그리드 노트) 영역을 확장하여 넉넉하게 풀이를 작성합니다.
        풀이 길이에 맞춰 세로 높이도 지능적으로 조절합니다.
        그래프가 있을 경우 모눈종이 위에 자연스러운 손글씨 필기풍으로 함께 렌더링합니다.
        """
        orig_w, orig_h = base_img.size
        # 모눈노트 확장 너비: 최소 650px을 주어 수식과 풀이가 시원하게 들어가도록 보장
        ext_w = max(650, int(orig_w * 0.9))
        font_size = max(20, min(25, int(ext_w * 0.034)))
        line_spacing = int(font_size * 0.45)
        wrap_w = ext_w - 75

        lines_to_draw: List[str] = [
            "[풀이 노트]",
            "",
        ]
        title = solution_data.get("problem_title", "")
        if title:
            lines_to_draw.extend(self.engine.wrap_text(f"문제: {title}", font_name, font_size, wrap_w))
            lines_to_draw.append("")

        for step in solution_data.get("steps", []):
            lines_to_draw.extend(self.engine.wrap_text(step, font_name, font_size, wrap_w))

        ans = format_answer(solution_data.get("final_answer", ""))
        if ans:
            lines_to_draw.append("")
            lines_to_draw.extend(self.engine.wrap_text(f"★ 정답: {ans}", font_name, font_size, wrap_w))

        tip = solution_data.get("tip", "")
        if tip:
            lines_to_draw.append("")
            lines_to_draw.extend(self.engine.wrap_text(f"Tip: {tip}", font_name, font_size, wrap_w))

        # 다이어그램 렌더링 시도
        diag_img = None
        diagram_data = solution_data.get("diagram")
        if diagram_data and (solution_data.get("has_diagram") or isinstance(diagram_data, dict)):
            try:
                diag_max_w = min(ext_w - 70, 440)
                diag_img = self.diagram_engine.render_diagram(diagram_data, font_name, pen_style, max_width=diag_max_w)
            except Exception as e:
                print(f"[!] 모눈노트 다이어그램 렌더링 오류: {e}")
                diag_img = None

        text_block_h = len(lines_to_draw) * (font_size + line_spacing)
        if diag_img:
            total_text_h = text_block_h + diag_img.height + 140
        else:
            total_text_h = text_block_h + 120

        new_h = max(orig_h, total_text_h)
        new_w = orig_w + ext_w

        bg_rgb_base = sample_background_color(base_img)
        result = Image.new("RGBA", (new_w, new_h), bg_rgb_base + (255,))
        result.paste(base_img.convert("RGBA"), (0, 0))

        # 우측 그리드(모눈) 배경 생성
        grid_overlay = Image.new("RGBA", (ext_w, new_h), (253, 253, 253, 255))
        draw = ImageDraw.Draw(grid_overlay)
        grid_size = 24
        grid_color = (226, 232, 240, 255)
        for x in range(0, ext_w, grid_size):
            draw.line([(x, 0), (x, new_h)], fill=grid_color, width=1)
        for y in range(0, new_h, grid_size):
            draw.line([(0, y), (ext_w, y)], fill=grid_color, width=1)

        # 왼쪽 경계선 그림자 효과
        for i in range(14):
            alpha = int(45 * (1 - i / 14))
            draw.line([(i, 0), (i, new_h)], fill=(0, 0, 0, alpha), width=1)

        result.alpha_composite(grid_overlay, (orig_w, 0))

        if diag_img is not None:
            head_lines = [
                "[풀이 노트]",
                "",
            ]
            if title:
                head_lines.extend(self.engine.wrap_text(f"문제: {title}", font_name, font_size, wrap_w))
                head_lines.append("")

            result_with_text, end_pos = self.engine.draw_handwritten_text(
                base_img=result,
                text_lines=head_lines,
                start_pos=(orig_w + 35, 40),
                font_name=font_name,
                font_size=font_size,
                pen_style_name=pen_style,
                line_spacing=line_spacing,
                apply_jitter=True
            )
            diag_x = orig_w + max(20, (ext_w - diag_img.width) // 2)
            diag_y = end_pos[1] + 12
            result_with_text.alpha_composite(diag_img, (int(diag_x), int(diag_y)))

            remaining_lines = []
            for step in solution_data.get("steps", []):
                remaining_lines.extend(self.engine.wrap_text(step, font_name, font_size, wrap_w))
            if ans:
                remaining_lines.append("")
                remaining_lines.extend(self.engine.wrap_text(f"★ 정답: {ans}", font_name, font_size, wrap_w))
            if tip:
                remaining_lines.append("")
                remaining_lines.extend(self.engine.wrap_text(f"Tip: {tip}", font_name, font_size, wrap_w))

            rem_pos = (orig_w + 35, int(diag_y + diag_img.height + 16))
            result_with_text, end_pos = self.engine.draw_handwritten_text(
                base_img=result_with_text,
                text_lines=remaining_lines,
                start_pos=rem_pos,
                font_name=font_name,
                font_size=font_size,
                pen_style_name=pen_style,
                line_spacing=line_spacing,
                apply_jitter=True
            )
            result_with_text = self._draw_ans_circle_if_exists(
                img=result_with_text,
                lines=remaining_lines,
                ans=ans,
                start_pos=rem_pos,
                font_name=font_name,
                font_size=font_size,
                line_spacing=line_spacing,
                pen_style=pen_style
            )
            return result_with_text.convert("RGB")
        else:
            base_pos = (orig_w + 35, 40)
            result_with_text, end_pos = self.engine.draw_handwritten_text(
                base_img=result,
                text_lines=lines_to_draw,
                start_pos=base_pos,
                font_name=font_name,
                font_size=font_size,
                pen_style_name=pen_style,
                line_spacing=line_spacing,
                apply_jitter=True
            )
            result_with_text = self._draw_ans_circle_if_exists(
                img=result_with_text,
                lines=lines_to_draw,
                ans=ans,
                start_pos=base_pos,
                font_name=font_name,
                font_size=font_size,
                line_spacing=line_spacing,
                pen_style=pen_style
            )
            return result_with_text.convert("RGB")



"""
손글씨 스타일 수학/과학 그래프 및 다이어그램 렌더링 엔진
학생이나 선생님이 공책이나 시험지 여백에 펜으로 직접 스케치한 듯한
자연스러운 필기풍 그래프(좌표평면, 함수곡선, 수직선, 기하도형, 벤다이어그램)를 생성합니다.
"""
import math
import random
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from core.handwriting_engine import HandwritingEngine, PEN_STYLES, FONT_MAP
from core.safe_math import safe_eval

class HandwrittenDiagramEngine:
    def __init__(self, handwriting_engine: HandwritingEngine):
        self.hw_engine = handwriting_engine

    def _get_pen_color_and_width(self, pen_style_name: str) -> Tuple[Tuple[int, int, int, int], int]:
        pen_info = PEN_STYLES.get(pen_style_name) or list(PEN_STYLES.values())[0]
        color = pen_info.get("color", (25, 25, 25, 245))
        stroke_w = 2
        return color, stroke_w

    def _draw_text(self, draw: ImageDraw.ImageDraw, pos: Tuple[float, float], text: str, fill, font, font_name: str):
        safe_text = self.hw_engine.sanitize_math_text(str(text), font_name)
        draw.text(pos, safe_text, fill=fill, font=font)

    def _draw_wobbly_line(
        self,
        draw: ImageDraw.ImageDraw,
        pt1: Tuple[float, float],
        pt2: Tuple[float, float],
        color: Tuple[int, int, int, int],
        width: int = 2,
        wobble_strength: float = 1.0,
        dashed: bool = False
    ):
        """사람의 손 떨림과 필기 압력을 재현하는 자연스러운 손글씨 직선을 그립니다."""
        x1, y1 = pt1
        x2, y2 = pt2
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 1:
            return

        steps = max(3, int(length / 8))
        dx = (x2 - x1) / steps
        dy = (y2 - y1) / steps

        # 법선 벡터 (수직 흔들림 방향)
        nx = -dy / (math.hypot(dx, dy) + 1e-6)
        ny = dx / (math.hypot(dx, dy) + 1e-6)

        points = [(x1, y1)]
        for i in range(1, steps):
            # 중심부에서 살짝 흔들림이 더 큼
            factor = math.sin(math.pi * i / steps) * wobble_strength
            jitter = random.uniform(-0.8, 0.8) * factor
            px = x1 + dx * i + nx * jitter
            py = y1 + dy * i + ny * jitter
            points.append((px, py))
        points.append((x2, y2))

        if dashed:
            # 점선 그리기
            dash_len = 8
            gap_len = 6
            cur_dist = 0
            is_drawing = True
            for i in range(len(points) - 1):
                seg_len = math.hypot(points[i+1][0] - points[i][0], points[i+1][1] - points[i][1])
                cur_dist += seg_len
                if is_drawing:
                    draw.line([points[i], points[i+1]], fill=color, width=max(1, width - 1))
                    if cur_dist >= dash_len:
                        is_drawing = False
                        cur_dist = 0
                else:
                    if cur_dist >= gap_len:
                        is_drawing = True
                        cur_dist = 0
        else:
            for i in range(len(points) - 1):
                draw.line([points[i], points[i+1]], fill=color, width=width)

    def _draw_arrow_head(
        self,
        draw: ImageDraw.ImageDraw,
        tip: Tuple[float, float],
        angle_rad: float,
        color: Tuple[int, int, int, int],
        size: float = 10,
        width: int = 2
    ):
        """손으로 그린 듯한 화살표 머리를 그립니다."""
        tx, ty = tip
        left_angle = angle_rad + math.pi - math.radians(26)
        right_angle = angle_rad + math.pi + math.radians(26)

        p_left = (tx + size * math.cos(left_angle), ty + size * math.sin(left_angle))
        p_right = (tx + size * math.cos(right_angle), ty + size * math.sin(right_angle))

        self._draw_wobbly_line(draw, tip, p_left, color, width=width, wobble_strength=0.5)
        self._draw_wobbly_line(draw, tip, p_right, color, width=width, wobble_strength=0.5)

    def _draw_hatching(
        self,
        draw: ImageDraw.ImageDraw,
        polygon: List[Tuple[float, float]],
        color: Tuple[int, int, int, int],
        spacing: int = 10
    ):
        """영역에 손으로 그은 듯한 빗금(Hatching)을 채웁니다."""
        if len(polygon) < 3:
            return
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        hatch_color = (color[0], color[1], color[2], max(40, color[3] - 70))
        # y = x + c 형태의 대각선 빗금
        c_min = int(min_y - max_x)
        c_max = int(max_y - min_x)

        from PIL import ImagePath
        # 마스크를 이용한 안전한 빗금 렌더링
        w = int(max_x - min_x + 20)
        h = int(max_y - min_y + 20)
        if w <= 0 or h <= 0:
            return

        mask = Image.new("L", (w, h), 0)
        m_draw = ImageDraw.Draw(mask)
        shifted_poly = [(p[0] - min_x + 10, p[1] - min_y + 10) for p in polygon]
        m_draw.polygon(shifted_poly, fill=255)

        hatch_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        h_draw = ImageDraw.Draw(hatch_layer)
        for c in range(-w, h + w, spacing):
            p1 = (0, c)
            p2 = (w, c + w)
            h_draw.line([p1, p2], fill=hatch_color, width=1)

        # 마스크 합성 후 원본에 붙이기
        hatch_masked = Image.composite(hatch_layer, Image.new("RGBA", (w, h), (0,0,0,0)), mask)
        # alpha_composite를 쓰기 위해 호출처에서 처리하거나 직접 붙임
        return hatch_masked, (int(min_x - 10), int(min_y - 10))

    def render_coordinate_plane(
        self,
        diagram_data: Dict[str, Any],
        font_name: str,
        pen_style: str,
        width: int = 440,
        height: int = 320
    ) -> Image.Image:
        """좌표평면 및 함수 곡선, 점, 점선을 정밀하고 자연스럽게 렌더링합니다."""
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        main_color, stroke_w = self._get_pen_color_and_width(pen_style)
        axis_color = (max(0, main_color[0] - 10), max(0, main_color[1] - 10), max(0, main_color[2] - 10), min(230, main_color[3]))
        accent_blue = (37, 99, 235, 235)
        accent_red = (220, 38, 38, 235)

        # x, y 범위 설정
        x_rng = diagram_data.get("x_range", [-2, 5])
        y_rng = diagram_data.get("y_range", [-2, 5])
        x_min, x_max = float(x_rng[0]), float(x_rng[1])
        y_min, y_max = float(y_rng[0]), float(y_rng[1])

        # 여백 (마진)
        pad_l, pad_r = 45, 35
        pad_t, pad_b = 42, 35
        plot_w = width - pad_l - pad_r
        plot_h = height - pad_t - pad_b

        def to_screen(x: float, y: float) -> Tuple[float, float]:
            sx = pad_l + (x - x_min) / (x_max - x_min) * plot_w
            sy = pad_t + (y_max - y) / (y_max - y_min) * plot_h
            return sx, sy

        # 원점 위치
        ox, oy = to_screen(0, 0)
        # 화면 내에 축이 존재하도록 클램핑
        axis_y = max(pad_t, min(height - pad_b, oy))
        axis_x = max(pad_l, min(width - pad_r, ox))

        # 1. x축 및 y축 그리기
        # x축
        self._draw_wobbly_line(draw, (pad_l - 15, axis_y), (width - pad_r + 20, axis_y), axis_color, width=stroke_w, wobble_strength=0.8)
        self._draw_arrow_head(draw, (width - pad_r + 20, axis_y), 0, axis_color, size=9, width=stroke_w)
        # y축
        self._draw_wobbly_line(draw, (axis_x, height - pad_b + 15), (axis_x, pad_t - 14), axis_color, width=stroke_w, wobble_strength=0.8)
        self._draw_arrow_head(draw, (axis_x, pad_t - 14), -math.pi / 2, axis_color, size=9, width=stroke_w)

        # 축 레이블 (x, y, O)
        font = self.hw_engine.load_font(font_name, 16)
        self._draw_text(draw, (width - pad_r + 14, axis_y + 4), "x", axis_color, font, font_name)
        self._draw_text(draw, (axis_x + 8, pad_t - 16), "y", axis_color, font, font_name)
        self._draw_text(draw, (axis_x - 14, axis_y + 4), "O", axis_color, font, font_name)

        # 2. 음영 영역(Shaded region / 정적분 넓이 등)
        shaded = diagram_data.get("shaded_region")
        if shaded:
            s_xmin = float(shaded.get("x_min", x_min))
            s_xmax = float(shaded.get("x_max", x_max))
            y_low_expr = str(shaded.get("y_lower", "0")).replace("^", "**")
            y_up_expr = str(shaded.get("y_upper", "0")).replace("^", "**")
            xs_s = np.linspace(s_xmin, s_xmax, 60)
            poly_pts = []
            try:
                y_lows = safe_eval(y_low_expr, xs_s)
                if isinstance(y_lows, (int, float)):
                    y_lows = np.full_like(xs_s, y_lows)
                for px, py in zip(xs_s, y_lows):
                    poly_pts.append(to_screen(float(px), float(py)))
                y_ups = safe_eval(y_up_expr, xs_s)
                if isinstance(y_ups, (int, float)):
                    y_ups = np.full_like(xs_s, y_ups)
                for px, py in zip(reversed(xs_s), reversed(y_ups)):
                    poly_pts.append(to_screen(float(px), float(py)))
                
                if len(poly_pts) >= 3:
                    hatch = self._draw_hatching(draw, poly_pts, accent_blue, spacing=8)
                    if hatch:
                        img.alpha_composite(hatch[0], hatch[1])
            except Exception as e:
                print(f"[!] 음영 영역 계산 오류: {e}")

        # 3. 보조선(Dashed Lines)
        for line in diagram_data.get("lines", []):
            lx1, ly1 = float(line.get("x1", 0)), float(line.get("y1", 0))
            lx2, ly2 = float(line.get("x2", 0)), float(line.get("y2", 0))
            p1 = to_screen(lx1, ly1)
            p2 = to_screen(lx2, ly2)
            dashed = line.get("style", "dashed") == "dashed"
            self._draw_wobbly_line(draw, p1, p2, (120, 130, 145, 190), width=max(1, stroke_w - 1), dashed=dashed)

        # 4. 함수 곡선들(Functions)
        funcs = diagram_data.get("functions", [])
        for f_idx, f_info in enumerate(funcs):
            expr = f_info.get("expr", "")
            f_color = accent_blue if f_info.get("color") == "blue" else (accent_red if f_info.get("color") == "red" else main_color)
            f_xmin = float(f_info.get("x_min", x_min))
            f_xmax = float(f_info.get("x_max", x_max))

            # 곡선 점 샘플링
            xs = np.linspace(f_xmin, f_xmax, 160)
            pts = []
            try:
                clean_expr = expr.replace("^", "**")
                ys = safe_eval(clean_expr, xs)
                if isinstance(ys, (int, float)):
                    ys = np.full_like(xs, ys)

                for px, py in zip(xs, ys):
                    if np.isnan(py) or np.isinf(py):
                        continue
                    if (y_min - 0.1) <= py <= (y_max + 0.1):
                        pts.append(to_screen(float(px), float(py)))
            except Exception as e:
                print(f"[!] 함수식 계산 오류 ({expr}): {e}")
                pts = []

            # 부드러운 손글씨 곡선 렌더링
            if len(pts) >= 2:
                for i in range(len(pts) - 1):
                    p_start = pts[i]
                    p_end = pts[i+1]
                    if math.hypot(p_end[0] - p_start[0], p_end[1] - p_start[1]) < 80:
                        draw.line([p_start, p_end], fill=f_color, width=stroke_w + 1)

            # 함수 레이블
            f_label = f_info.get("label", "")
            if f_label and pts:
                lbl_pt = pts[-1] if len(pts) < 140 else pts[int(len(pts) * 0.85)]
                self._draw_text(draw, (lbl_pt[0] + 6, lbl_pt[1] - 16), f_label, f_color, font, font_name)

        # 5. 주요 특징점(Points) & 점 좌표 레이블
        for pt in diagram_data.get("points", []):
            px, py = float(pt.get("x", 0)), float(pt.get("y", 0))
            sx, sy = to_screen(px, py)
            radius = max(3, stroke_w + 1)
            draw.ellipse([sx - radius, sy - radius, sx + radius, sy + radius], fill=main_color, outline=main_color)

            # 레이블
            p_label = pt.get("label", "")
            if p_label:
                pos_dx = 5
                pos_dy = 4
                if abs(py) < 0.1:
                    pos_dy = 6
                    pos_dx = -6
                elif abs(px) < 0.1:
                    pos_dx = -18
                    pos_dy = -8
                self._draw_text(draw, (sx + pos_dx, sy + pos_dy), p_label, main_color, font, font_name)

        # 6. 그래프 타이틀 (상단 여백에 깔끔하게 배치)
        diag_title = diagram_data.get("title", "")
        if diag_title:
            t_font = self.hw_engine.load_font(font_name, 16)
            self._draw_text(draw, (20, 6), f"[{diag_title}]", main_color, t_font, font_name)

        return img

    def render_number_line(
        self,
        diagram_data: Dict[str, Any],
        font_name: str,
        pen_style: str,
        width: int = 420,
        height: int = 150
    ) -> Image.Image:
        """수직선 및 부등식 범위를 손글씨 스타일로 렌더링합니다."""
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        main_color, stroke_w = self._get_pen_color_and_width(pen_style)
        accent_blue = (37, 99, 235, 235)

        nl_info = diagram_data.get("number_line", diagram_data)
        rng = nl_info.get("range", [-3, 5])
        x_min, x_max = float(rng[0]), float(rng[1])

        pad_x = 45
        axis_y = height // 2 + 10
        line_w = width - pad_x * 2

        def to_screen_x(val: float) -> float:
            return pad_x + (val - x_min) / (x_max - x_min) * line_w

        # 수직선 본체
        self._draw_wobbly_line(draw, (pad_x - 15, axis_y), (width - pad_x + 15, axis_y), main_color, width=stroke_w)
        self._draw_arrow_head(draw, (width - pad_x + 15, axis_y), 0, main_color, size=8, width=stroke_w)
        self._draw_arrow_head(draw, (pad_x - 15, axis_y), math.pi, main_color, size=8, width=stroke_w)

        font = self.hw_engine.load_font(font_name, 16)
        draw.text((width - pad_x + 12, axis_y + 4), "x", fill=main_color, font=font)

        # 눈금 및 정수 라벨
        int_start = math.ceil(x_min)
        int_end = math.floor(x_max)
        for val in range(int_start, int_end + 1):
            sx = to_screen_x(val)
            self._draw_wobbly_line(draw, (sx, axis_y - 4), (sx, axis_y + 4), main_color, width=max(1, stroke_w - 1))
            draw.text((sx - 5, axis_y + 7), str(val), fill=main_color, font=font)

        # 구간 화살표 (Intervals)
        intervals = nl_info.get("intervals", [])
        bar_y = axis_y - 32
        for idx, inter in enumerate(intervals):
            start_val = float(inter.get("start", x_min))
            end_val = float(inter.get("end", x_max))
            incl_s = inter.get("include_start", True)
            incl_e = inter.get("include_end", True)
            direction = inter.get("direction", "between")

            sx_start = to_screen_x(start_val)
            sx_end = to_screen_x(end_val)

            # 수직 기둥 및 수평선
            self._draw_wobbly_line(draw, (sx_start, axis_y), (sx_start, bar_y), accent_blue, width=stroke_w)
            if direction == "between":
                self._draw_wobbly_line(draw, (sx_end, axis_y), (sx_end, bar_y), accent_blue, width=stroke_w)
                self._draw_wobbly_line(draw, (sx_start, bar_y), (sx_end, bar_y), accent_blue, width=stroke_w + 1)
                # 끝점 원
                rad = 4
                s_fill = accent_blue if incl_s else (255, 255, 255, 255)
                e_fill = accent_blue if incl_e else (255, 255, 255, 255)
                draw.ellipse([sx_start - rad, bar_y - rad, sx_start + rad, bar_y + rad], fill=s_fill, outline=accent_blue, width=2)
                draw.ellipse([sx_end - rad, bar_y - rad, sx_end + rad, bar_y + rad], fill=e_fill, outline=accent_blue, width=2)

                # 빗금 채우기 (Hatching)
                poly = [(sx_start, axis_y), (sx_start, bar_y), (sx_end, bar_y), (sx_end, axis_y)]
                hatch = self._draw_hatching(draw, poly, accent_blue, spacing=8)
                if hatch:
                    img.alpha_composite(hatch[0], hatch[1])

            elif direction == "right":
                self._draw_wobbly_line(draw, (sx_start, bar_y), (width - pad_x + 10, bar_y), accent_blue, width=stroke_w + 1)
                self._draw_arrow_head(draw, (width - pad_x + 10, bar_y), 0, accent_blue, size=7, width=stroke_w)
                rad = 4
                s_fill = accent_blue if incl_s else (255, 255, 255, 255)
                draw.ellipse([sx_start - rad, bar_y - rad, sx_start + rad, bar_y + rad], fill=s_fill, outline=accent_blue, width=2)

        return img

    def render_geometry(
        self,
        diagram_data: Dict[str, Any],
        font_name: str,
        pen_style: str,
        width: int = 420,
        height: int = 260
    ) -> Image.Image:
        """기하 도형(삼각형, 사각형, 원)을 손글씨 스타일로 렌더링합니다."""
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        main_color, stroke_w = self._get_pen_color_and_width(pen_style)
        accent_blue = (37, 99, 235, 235)
        font = self.hw_engine.load_font(font_name, 16)
        
        shapes = diagram_data.get("shapes") or [diagram_data.get("geometry", {})]
        if not shapes or shapes == [{}]:
            shapes = [{"type": "triangle", "vertices": [[0, 0], [4, 0], [0, 3]], "labels": ["A", "B", "C"]}]

        for shape in shapes:
            stype = shape.get("type", "triangle")
            if "triangle" in stype or "삼각형" in stype:
                v = shape.get("vertices", [[0, 0], [4, 0], [0, 3]])
                lbls = shape.get("labels", ["A", "B", "C"])
                
                xs = [pt[0] for pt in v]
                ys = [pt[1] for pt in v]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                span_x = max(1e-3, max_x - min_x)
                span_y = max(1e-3, max_y - min_y)
                
                pad_x, pad_y = 50, 45
                avail_w = width - pad_x * 2
                avail_h = height - pad_y * 2
                scale = min(avail_w / span_x, avail_h / span_y) * 0.85
                
                cx = width / 2
                cy = height / 2 + 10
                mid_vx = (min_x + max_x) / 2
                mid_vy = (min_y + max_y) / 2
                
                screen_pts = []
                for pt in v:
                    sx = cx + (pt[0] - mid_vx) * scale
                    sy = cy - (pt[1] - mid_vy) * scale
                    screen_pts.append((sx, sy))
                
                for i in range(len(screen_pts)):
                    p1 = screen_pts[i]
                    p2 = screen_pts[(i + 1) % len(screen_pts)]
                    self._draw_wobbly_line(draw, p1, p2, main_color, width=stroke_w)
                
                for idx, (sx, sy) in enumerate(screen_pts):
                    lbl = lbls[idx] if idx < len(lbls) else ""
                    dx = 8 if sx >= cx else -16
                    dy = -18 if sy <= cy else 8
                    draw.text((sx + dx, sy + dy), lbl, fill=main_color, font=font)
                    
            elif "circle" in stype or "원" in stype:
                cx, cy = width / 2, height / 2 + 10
                r = min(width, height) * 0.35
                circ_pts = []
                steps = 64
                for i in range(steps + 1):
                    theta = 2 * math.pi * i / steps
                    jr = r + random.uniform(-0.8, 0.8)
                    circ_pts.append((cx + jr * math.cos(theta), cy + jr * math.sin(theta)))
                for i in range(len(circ_pts) - 1):
                    draw.line([circ_pts[i], circ_pts[i+1]], fill=main_color, width=stroke_w)
                
                draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=main_color)
                draw.text((cx + 6, cy - 14), "O", fill=main_color, font=font)
                
        diag_title = diagram_data.get("title", "")
        if diag_title:
            t_font = self.hw_engine.load_font(font_name, 17)
            draw.text((35, 8), f"▶ {diag_title}", fill=main_color, font=t_font)
            
        return img

    def render_venn(
        self,
        diagram_data: Dict[str, Any],
        font_name: str,
        pen_style: str,
        width: int = 420,
        height: int = 240
    ) -> Image.Image:
        """벤 다이어그램(집합 A, B)을 손글씨 스타일로 렌더링합니다."""
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        main_color, stroke_w = self._get_pen_color_and_width(pen_style)
        accent_blue = (37, 99, 235, 235)
        font = self.hw_engine.load_font(font_name, 16)
        
        # 전체집합 U 사각형 박스
        self._draw_wobbly_line(draw, (20, 24), (width - 20, 24), main_color, width=stroke_w)
        self._draw_wobbly_line(draw, (width - 20, 24), (width - 20, height - 16), main_color, width=stroke_w)
        self._draw_wobbly_line(draw, (width - 20, height - 16), (20, height - 16), main_color, width=stroke_w)
        self._draw_wobbly_line(draw, (20, height - 16), (20, 24), main_color, width=stroke_w)
        draw.text((28, 28), "U", fill=main_color, font=font)
        
        # 두 집합 A, B 원
        cy = height / 2 + 6
        r = 62
        c1x = width / 2 - 46
        c2x = width / 2 + 46
        
        def draw_wobbly_circle(cx, cy, r, color):
            pts = []
            steps = 48
            for i in range(steps + 1):
                theta = 2 * math.pi * i / steps
                jr = r + random.uniform(-0.8, 0.8)
                pts.append((cx + jr * math.cos(theta), cy + jr * math.sin(theta)))
            for i in range(len(pts) - 1):
                draw.line([pts[i], pts[i+1]], fill=color, width=stroke_w)
                
        draw_wobbly_circle(c1x, cy, r, main_color)
        draw_wobbly_circle(c2x, cy, r, main_color)
        
        draw.text((c1x - 30, cy - r - 15), "A", fill=main_color, font=font)
        draw.text((c2x + 20, cy - r - 15), "B", fill=main_color, font=font)
        
        # 교집합 음영 표시 옵션
        highlight = diagram_data.get("highlight", "")
        if "교집합" in highlight or "intersection" in highlight or "A∩B" in highlight:
            m1 = Image.new("L", (width, height), 0)
            m2 = Image.new("L", (width, height), 0)
            ImageDraw.Draw(m1).ellipse([c1x - r, cy - r, c1x + r, cy + r], fill=255)
            ImageDraw.Draw(m2).ellipse([c2x - r, cy - r, c2x + r, cy + r], fill=255)
            from PIL import ImageChops
            inter_mask = ImageChops.multiply(m1, m2)
            
            hatch_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            h_draw = ImageDraw.Draw(hatch_layer)
            for c in range(-width, height + width, 8):
                h_draw.line([(0, c), (width, c + width)], fill=accent_blue, width=1)
            hatch_masked = Image.composite(hatch_layer, Image.new("RGBA", (width, height), (0,0,0,0)), inter_mask)
            img.alpha_composite(hatch_masked, (0, 0))
            
        labels = diagram_data.get("labels", {})
        if "A" in labels:
            draw.text((c1x - 30, cy), str(labels["A"]), fill=main_color, font=font)
        if "intersection" in labels or "A∩B" in labels:
            inter_val = labels.get("intersection", labels.get("A∩B"))
            draw.text((width / 2 - 6, cy), str(inter_val), fill=accent_blue, font=font)
        if "B" in labels:
            draw.text((c2x + 18, cy), str(labels["B"]), fill=main_color, font=font)
            
        diag_title = diagram_data.get("title", "")
        if diag_title:
            t_font = self.hw_engine.load_font(font_name, 17)
            draw.text((35, 6), f"▶ {diag_title}", fill=main_color, font=t_font)
            
        return img

    def render_dual_graph(
        self,
        diagram_data: Dict[str, Any],
        font_name: str,
        pen_style: str,
        width: int = 440,
        height: int = 400
    ) -> Image.Image:
        """
        도함수 f(x)와 원함수 g(x) 등 2개의 함수 그래프를 위아래로 나란히 배치하고,
        영점(Roots)에서 극값/변곡점으로 세로 점선 지시선을 연결하여
        수능 1타 강사의 실전 연계 그래프를 완벽하게 렌더링합니다.
        """
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        main_color, stroke_w = self._get_pen_color_and_width(pen_style)
        axis_color = (max(0, main_color[0] - 10), max(0, main_color[1] - 10), max(0, main_color[2] - 10), min(230, main_color[3]))
        accent_blue = (18, 48, 145, 240)
        accent_green = (34, 139, 34, 220)
        accent_red = (205, 40, 40, 210)
        font = self.hw_engine.load_font(font_name, 16)
        lbl_font = self.hw_engine.load_font(font_name, 15)
        title_font = self.hw_engine.load_font(font_name, 17)

        # 1. 상단 그래프 설정
        top_data = diagram_data.get("top_graph", {})
        top_y_center = int(height * 0.22)
        top_x_left = 35
        top_x_right = width - 35
        cx = (top_x_left + top_x_right) // 2

        # 상단 x축
        self._draw_wobbly_line(draw, (top_x_left, top_y_center), (top_x_right, top_y_center), axis_color, width=stroke_w)

        # 상단 함수 곡선
        x_scale = 55
        funcs_top = top_data.get("functions", [])
        if not funcs_top:
            funcs_top = [{"expr": "0.5*x**2 - 0.7", "color": "blue", "label": "f(x)"}]

        for f_info in funcs_top:
            expr = f_info.get("expr", "0.5*x**2 - 0.7").replace("^", "**")
            f_color = accent_blue if f_info.get("color") == "blue" else main_color
            xs = np.linspace(-2.2, 2.2, 90)
            pts_top = []
            try:
                ys = safe_eval(expr, xs)
                if isinstance(ys, (int, float)):
                    ys = np.full_like(xs, ys)
                for x_val, y_val in zip(xs, ys):
                    px = cx + float(x_val) * x_scale
                    py = top_y_center - float(y_val) * 40
                    if 15 <= py <= top_y_center + 45:
                        pts_top.append((px, py))
            except Exception as e:
                print(f"[!] 상단 곡선 계산 오류: {e}")

            if len(pts_top) >= 2:
                for i in range(len(pts_top) - 1):
                    draw.line([pts_top[i], pts_top[i+1]], fill=f_color, width=stroke_w + 1)

            lbl = f_info.get("label", "f(x)")
            if lbl:
                self._draw_text(draw, (top_x_right - 35, top_y_center - 45), lbl, f_color, title_font, font_name)

        # 상단 부호 (+, -)
        signs = top_data.get("signs", [
            {"x": -1.5, "text": "+"},
            {"x": 0, "text": "-"},
            {"x": 1.5, "text": "+"}
        ])
        for s in signs:
            sx = cx + float(s.get("x", 0)) * x_scale
            sy = top_y_center - 22 if s.get("text") == "+" else top_y_center + 5
            self._draw_text(draw, (sx - 4, sy), s.get("text", "+"), main_color, font, font_name)

        # 상단 특징점 (예: (0, -c))
        for pt in top_data.get("points", [{"x": 0, "y": -0.7, "label": "(0,-c)"}]):
            px = cx + float(pt.get("x", 0)) * x_scale
            py = top_y_center - float(pt.get("y", 0)) * 40
            draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=main_color)
            p_lbl = pt.get("label", "")
            if p_lbl:
                self._draw_text(draw, (px - 16, py + 5), p_lbl, main_color, lbl_font, font_name)

        # 2. 하단 그래프 설정
        bot_data = diagram_data.get("bottom_graph", {})
        bot_y_center = int(height * 0.68)
        bot_x_left = 35
        bot_x_right = width - 35

        # 하단 x축
        self._draw_wobbly_line(draw, (bot_x_left, bot_y_center), (bot_x_right, bot_y_center), axis_color, width=stroke_w)

        # 세로 점선 지시선 (상단 영점 -> 하단 극값)
        connectors = diagram_data.get("connectors", [-1.18, 0.0, 1.18])
        for c_x in connectors:
            line_x = cx + float(c_x) * x_scale
            self._draw_wobbly_line(draw, (line_x, top_y_center), (line_x, bot_y_center - 32), (130, 150, 185, 180), width=1, dashed=True)

        # 수평 기준선 (Peak Height)
        self._draw_wobbly_line(draw, (cx - 100, bot_y_center - 32), (cx + 100, bot_y_center - 32), (130, 150, 185, 170), width=1, dashed=True)

        # 하단 사각형 (Rectangle highlight)
        rect_info = bot_data.get("rectangle", {"x1": -1.6, "y1": 0, "x2": 1.6, "y2": 1.5, "color": "green"})
        if rect_info:
            r_x1 = cx + float(rect_info.get("x1", -1.6)) * (x_scale * 0.95)
            r_x2 = cx + float(rect_info.get("x2", 1.6)) * (x_scale * 0.95)
            r_top = bot_y_center - 32
            r_bot = bot_y_center
            self._draw_wobbly_line(draw, (r_x1, r_top), (r_x2, r_top), accent_green, width=2)
            self._draw_wobbly_line(draw, (r_x1, r_top), (r_x1, r_bot), accent_green, width=2)
            self._draw_wobbly_line(draw, (r_x2, r_top), (r_x2, r_bot), accent_green, width=2)

            # 빗금 채우기 (Hatching)
            for c in range(-width, height + width, 8):
                p1 = (c, r_top)
                p2 = (c + 32, r_bot)
                if r_x1 <= p1[0] <= r_x2 or r_x1 <= p2[0] <= r_x2:
                    draw.line([max(r_x1, p1[0]), r_top, min(r_x2, p2[0]), r_bot], fill=accent_red, width=1)

        # 하단 함수 곡선 (g(x))
        funcs_bot = bot_data.get("functions", [])
        if not funcs_bot:
            funcs_bot = [{"expr": "-(x**2 - 1.4)**2 + 1.96", "color": "blue", "label": "g(x)"}]

        for f_info in funcs_bot:
            expr = f_info.get("expr", "-(x**2 - 1.4)**2 + 1.96").replace("^", "**")
            f_color = accent_blue if f_info.get("color") == "blue" else main_color
            xs_b = np.linspace(-2.2, 2.2, 100)
            pts_bot = []
            try:
                ys = safe_eval(expr, xs_b)
                if isinstance(ys, (int, float)):
                    ys = np.full_like(xs_b, ys)
                for x_val, y_val in zip(xs_b, ys):
                    px = cx + float(x_val) * (x_scale * 0.95)
                    py = bot_y_center - float(y_val) * 16.5
                    if top_y_center + 30 <= py <= height - 10:
                        pts_bot.append((px, py))
            except Exception as e:
                print(f"[!] 하단 곡선 계산 오류: {e}")

            if len(pts_bot) >= 2:
                for i in range(len(pts_bot) - 1):
                    draw.line([pts_bot[i], pts_bot[i+1]], fill=f_color, width=stroke_w + 1)

            lbl = f_info.get("label", "g(x)")
            if lbl:
                self._draw_text(draw, (bot_x_right - 35, bot_y_center - 55), lbl, f_color, title_font, font_name)

        # 하단 점 및 레이블 (a1, a2, 0, a3, a4 등)
        pts_list = bot_data.get("points", [
            {"x": -1.9, "label": "a1", "sub_label": "= a"},
            {"x": -1.0, "label": "a2"},
            {"x": 0.0, "label": "0"},
            {"x": 1.0, "label": "a3"},
            {"x": 1.9, "label": "a4"}
        ])
        for p in pts_list:
            px = cx + float(p.get("x", 0)) * (x_scale * 0.95)
            draw.ellipse([px - 2.5, bot_y_center - 2.5, px + 2.5, bot_y_center + 2.5], fill=main_color)
            lbl = p.get("label", "")
            if lbl:
                self._draw_text(draw, (px - 6, bot_y_center + 6), lbl, main_color, lbl_font, font_name)
            sub = p.get("sub_label", "")
            if sub:
                self._draw_text(draw, (px - 6, bot_y_center + 24), sub, main_color, lbl_font, font_name)

        # 부가 노트 (예: m = 4)
        for note in bot_data.get("notes", [{"x": 1.5, "text": "m = 4"}]):
            nx = cx + float(note.get("x", 1.5)) * (x_scale * 0.95)
            self._draw_text(draw, (nx, bot_y_center + 45), note.get("text", "m = 4"), main_color, title_font, font_name)

        # 다이어그램 상단 타이틀
        diag_title = diagram_data.get("title", "")
        if diag_title:
            self._draw_text(draw, (20, 6), f"[{diag_title}]", main_color, font, font_name)

        return img

    def render_diagram(
        self,
        diagram_data: Dict[str, Any],
        font_name: str,
        pen_style: str,
        max_width: int = 440
    ) -> Optional[Image.Image]:
        """주어진 다이어그램 사양을 판별하여 적절한 손글씨 그래픽을 생성합니다."""
        if not diagram_data or not isinstance(diagram_data, dict):
            return None

        d_type = str(diagram_data.get("diagram_type") or diagram_data.get("type", "coordinate_plane")).lower()
        w = min(max_width, 450)

        if "dual" in d_type or "linked" in d_type or "연계" in d_type or "두함수" in d_type:
            return self.render_dual_graph(diagram_data, font_name, pen_style, width=w, height=400)
        elif "number_line" in d_type or "수직선" in d_type:
            return self.render_number_line(diagram_data, font_name, pen_style, width=w, height=140)
        elif "geometry" in d_type or "도형" in d_type or "triangle" in d_type or "circle" in d_type:
            return self.render_geometry(diagram_data, font_name, pen_style, width=w, height=250)
        elif "venn" in d_type or "집합" in d_type:
            return self.render_venn(diagram_data, font_name, pen_style, width=w, height=240)
        else:
            # 기본: 좌표평면 및 함수 그래프
            return self.render_coordinate_plane(diagram_data, font_name, pen_style, width=w, height=300)


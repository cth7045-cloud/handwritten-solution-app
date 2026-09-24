"""
다양한 레이아웃(빈 공간 여백 직접 쓰기, 포스트잇 메모지, 모눈노트 확장)으로
문제 본문을 가리지 않고 실제 시험지의 자연스러운 여백에 손글씨 풀이를 합성하는 모듈
"""
import random
from typing import Dict, Any, Tuple, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from .handwriting_engine import HandwritingEngine

POSTIT_COLORS = {
    "노란색": (255, 250, 195),
    "분홍색": (255, 225, 235),
    "민트색": (220, 250, 235),
    "하늘색": (225, 240, 255),
}

def detect_empty_region(base_img: Image.Image) -> Tuple[int, int, int, int, str]:
    """
    이미지 내 인쇄된 텍스트 위치를 지능적으로 분석하여
    문제를 가리지 않는 최적의 빈 여백 영역과 방향을 반환합니다.
    반환값: (start_x, start_y, avail_w, avail_h, layout_type['bottom' | 'right'])
    """
    orig_w, orig_h = base_img.size
    sw = 300
    sh = max(50, int(300 * orig_h / orig_w))
    small = base_img.convert("L").resize((sw, sh))
    arr = np.array(small)

    # 텍스트 픽셀 검출 (어두운 글자 영역)
    dark_mask = arr < 170

    # 상단 8% 헤더(제목선)와 하단 5% 페이지 번호는 제외하고 본문 텍스트 영역 탐색
    header_cutoff = int(sh * 0.09)
    footer_cutoff = int(sh * 0.94)
    content_mask = dark_mask[header_cutoff:footer_cutoff, :]

    text_rows, text_cols = np.where(content_mask)

    if len(text_rows) > 0:
        max_row = np.max(text_rows) + header_cutoff
        min_row = np.min(text_rows) + header_cutoff
        max_col = np.max(text_cols)
        min_col = np.min(text_cols)

        real_max_y = int((max_row / sh) * orig_h)
        real_max_x = int((max_col / sw) * orig_w)
        real_min_x = int((min_col / sw) * orig_w)
    else:
        # 텍스트가 안 잡힐 경우 기본 하단/우측
        real_max_y = int(orig_h * 0.35)
        real_max_x = int(orig_w * 0.5)
        real_min_x = int(orig_w * 0.05)

    # 1. 하단에 충분한 여백이 있는 경우 (모의고사 시험지 일반형: 문제가 상단에 있고 아래가 텅 빔)
    bottom_space = orig_h - real_max_y - 40
    if bottom_space >= int(orig_h * 0.40):
        start_x = max(60, real_min_x)
        start_y = real_max_y + 35
        avail_w = min(880, orig_w - start_x - 50)
        avail_h = bottom_space - 30
        return start_x, start_y, avail_w, avail_h, "bottom"

    # 2. 우측에 충분한 여백이 있는 경우 (문제집 2단 구성 중 우측 여백)
    right_space = orig_w - real_max_x - 40
    if right_space >= int(orig_w * 0.32):
        start_x = real_max_x + 35
        start_y = int(orig_h * 0.16)
        avail_w = right_space - 20
        avail_h = int(orig_h * 0.76)
        return start_x, start_y, avail_w, avail_h, "right"

    # 3. 그 외 기본 하단 배치
    start_x = int(orig_w * 0.08)
    start_y = max(int(orig_h * 0.4), real_max_y + 20)
    avail_w = int(orig_w * 0.84)
    avail_h = max(200, orig_h - start_y - 30)
    return start_x, start_y, avail_w, avail_h, "bottom"

class OverlayComposer:
    def __init__(self, engine: HandwritingEngine):
        self.engine = engine

    def compose_margin_mode(
        self,
        base_img: Image.Image,
        solution_data: Dict[str, Any],
        font_name: str,
        pen_style: str
    ) -> Image.Image:
        """
        일반 시험지의 자연스러운 빈 공간에 직접 손글씨를 적은 것처럼 합성합니다.
        (인위적인 박스나 메모지 없음)
        """
        orig_w, orig_h = base_img.size
        safe_x, start_y, avail_w, avail_h, layout_type = detect_empty_region(base_img)

        # 레이아웃에 따른 폰트 크기
        if layout_type == "bottom":
            font_size = max(19, min(25, int(orig_w * 0.022)))
            max_wrap_w = min(avail_w, 750)
        else:
            font_size = max(18, min(24, int(avail_w * 0.052)))
            max_wrap_w = avail_w - 20

        lines_to_draw = []
        title = solution_data.get("problem_title", "")
        if title:
            lines_to_draw.append(f"<{title}>")
            lines_to_draw.append("")
        
        for step in solution_data.get("steps", []):
            wrapped = self.engine.wrap_text(step, font_name, font_size, max_wrap_w)
            lines_to_draw.extend(wrapped)

        lines_to_draw.append("")
        ans = solution_data.get("final_answer", "")
        lines_to_draw.append(f"∴ 정답: {ans}")

        tip = solution_data.get("tip", "")
        if tip:
            lines_to_draw.append("")
            wrapped_tip = self.engine.wrap_text(tip, font_name, font_size, max_wrap_w)
            lines_to_draw.extend(wrapped_tip)

        # 여백 위치에 손글씨 렌더링
        result, end_pos = self.engine.draw_handwritten_text(
            base_img=base_img,
            text_lines=lines_to_draw,
            start_pos=(safe_x, start_y),
            font_name=font_name,
            font_size=font_size,
            pen_style_name=pen_style,
            line_spacing=8,
            apply_jitter=True
        )

        return result.convert("RGB")

    def compose_postit_mode(
        self,
        base_img: Image.Image,
        solution_data: Dict[str, Any],
        font_name: str,
        pen_style: str,
        postit_color_name: str = "노란색"
    ) -> Image.Image:
        """
        문제 지문을 가리지 않도록 빈 여백 위치에 포스트잇 메모지를 합성합니다.
        """
        orig_w, orig_h = base_img.size
        safe_x, start_y, avail_w, avail_h, layout_type = detect_empty_region(base_img)

        postit_w = min(480, max(360, int(avail_w * 0.65))) if layout_type == "bottom" else min(450, max(320, int(avail_w * 0.95)))
        postit_h = min(420, max(320, int(avail_h * 0.88)))

        bg_rgb = POSTIT_COLORS.get(postit_color_name, (255, 250, 195))

        # 포스트잇 생성
        postit = Image.new("RGBA", (postit_w, postit_h), bg_rgb + (255,))
        draw = ImageDraw.Draw(postit)

        tape_h = int(postit_h * 0.08)
        darker_color = (max(0, bg_rgb[0] - 15), max(0, bg_rgb[1] - 15), max(0, bg_rgb[2] - 15), 180)
        draw.rectangle([0, 0, postit_w, tape_h], fill=darker_color)

        font_size = max(16, min(22, int(postit_w * 0.046)))

        lines_to_draw = []
        title = solution_data.get("problem_title", "풀이 과정")
        lines_to_draw.append(f"[풀이] {title}")
        lines_to_draw.append("")

        for step in solution_data.get("steps", []):
            wrapped = self.engine.wrap_text(step, font_name, font_size, postit_w - 50)
            lines_to_draw.extend(wrapped)

        lines_to_draw.append("")
        ans = solution_data.get("final_answer", "")
        lines_to_draw.append(f"정답: {ans}")

        tip = solution_data.get("tip", "")
        if tip:
            lines_to_draw.append("")
            wrapped_tip = self.engine.wrap_text(tip, font_name, font_size, postit_w - 50)
            lines_to_draw.extend(wrapped_tip)

        postit_with_text, end_pos = self.engine.draw_handwritten_text(
            base_img=postit,
            text_lines=lines_to_draw,
            start_pos=(25, tape_h + 15),
            font_name=font_name,
            font_size=font_size,
            pen_style_name=pen_style,
            line_spacing=8,
            apply_jitter=True
        )

        # 그림자 및 회전
        angle = random.uniform(-1.5, 1.5)
        pad = 25
        shadow_box = Image.new("RGBA", (postit_w + pad * 2, postit_h + pad * 2), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow_box)
        sdraw.rectangle([pad + 4, pad + 8, pad + postit_w + 4, pad + postit_h + 8], fill=(0, 0, 0, 70))
        shadow_box = shadow_box.filter(ImageFilter.GaussianBlur(10))

        shadow_box.alpha_composite(postit_with_text, (pad, pad))
        rotated_postit = shadow_box.rotate(angle, resample=Image.BICUBIC, expand=True)

        # 배치 좌표 계산 (본문을 가리지 않는 빈 공간에 안착)
        result = base_img.convert("RGBA")
        if layout_type == "bottom":
            target_x = max(safe_x, int((orig_w - rotated_postit.width) / 2))
            target_y = min(orig_h - rotated_postit.height - 15, start_y + 10)
        else:
            target_x = max(safe_x - 10, orig_w - rotated_postit.width + 5)
            target_y = max(10, min(start_y, orig_h - rotated_postit.height - 15))

        result.alpha_composite(rotated_postit, (int(target_x), int(target_y)))
        return result.convert("RGB")

    def compose_notebook_extension_mode(
        self,
        base_img: Image.Image,
        solution_data: Dict[str, Any],
        font_name: str,
        pen_style: str
    ) -> Image.Image:
        """
        원본 이미지 우측에 모눈종이(그리드 노트) 영역을 확장하여 넉넉하게 풀이를 작성합니다.
        """
        orig_w, orig_h = base_img.size
        ext_w = int(orig_w * 0.75)
        new_w = orig_w + ext_w
        new_h = orig_h

        result = Image.new("RGBA", (new_w, new_h), (250, 250, 250, 255))
        result.paste(base_img.convert("RGBA"), (0, 0))

        draw = ImageDraw.Draw(result)
        grid_size = 25
        grid_color = (225, 232, 240, 255)
        for x in range(orig_w, new_w, grid_size):
            draw.line([(x, 0), (x, new_h)], fill=grid_color, width=1)
        for y in range(0, new_h, grid_size):
            draw.line([(orig_w, y), (new_w, y)], fill=grid_color, width=1)

        for i in range(15):
            alpha = int(40 * (1 - i / 15))
            draw.line([(orig_w + i, 0), (orig_w + i, new_h)], fill=(0, 0, 0, alpha), width=1)

        font_size = max(20, int(orig_w * 0.026))

        lines_to_draw = [
            "📝 [선생님 손글씨 풀이 노트]",
            "────────────────────────",
            f"문제: {solution_data.get('problem_title', '풀이')}",
            ""
        ]
        for step in solution_data.get("steps", []):
            wrapped = self.engine.wrap_text(step, font_name, font_size, ext_w - 70)
            lines_to_draw.extend(wrapped)

        lines_to_draw.append("")
        ans = solution_data.get("final_answer", "")
        lines_to_draw.append(f"★ 정답: {ans}")

        tip = solution_data.get("tip", "")
        if tip:
            lines_to_draw.append("")
            wrapped_tip = self.engine.wrap_text(tip, font_name, font_size, ext_w - 70)
            lines_to_draw.extend(wrapped_tip)

        result_with_text, end_pos = self.engine.draw_handwritten_text(
            base_img=result,
            text_lines=lines_to_draw,
            start_pos=(orig_w + 35, 40),
            font_name=font_name,
            font_size=font_size,
            pen_style_name=pen_style,
            line_spacing=12,
            apply_jitter=True
        )

        return result_with_text.convert("RGB")

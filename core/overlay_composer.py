"""
다양한 레이아웃(빈 공간 여백 직접 쓰기, 포스트잇 메모지, 모눈노트 확장)으로
문제 본문을 가리지 않고 실제 시험지의 자연스러운 여백에 손글씨 풀이를 합성하는 모듈
이미지가 좁거나 잘려 있는 경우(크롭 스크린샷 등) 지능적으로 캔버스를 확장하여 글씨가 잘리지 않도록 보장합니다.
"""
import random
from typing import Dict, Any, Tuple, Optional, List
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from .handwriting_engine import HandwritingEngine

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
        일반 시험지/문제집의 자연스러운 빈 공간에 직접 손글씨를 적은 것처럼 합성합니다.
        문제가 꽉 차있거나 좁게 크롭된 경우 캔버스를 아래로 스마트하게 확장하여
        글씨가 잘리거나 겹치지 않고 100% 완벽하게 표시되도록 보장합니다.
        """
        orig_w, orig_h = base_img.size
        min_x, min_y, max_x, max_y = detect_content_bounds(base_img)

        # 이미지 너비에 비례한 가독성 높은 폰트 크기 산출
        font_size = max(20, min(28, int(orig_w * 0.026)))
        line_spacing = int(font_size * 0.45)
        max_wrap_w = int(orig_w * 0.86)

        # 풀이 텍스트 라인 구성
        lines_to_draw: List[str] = []
        title = solution_data.get("problem_title", "")
        if title:
            lines_to_draw.append(f"<{title}>")
            lines_to_draw.append("")
        
        for step in solution_data.get("steps", []):
            wrapped = self.engine.wrap_text(step, font_name, font_size, max_wrap_w)
            lines_to_draw.extend(wrapped)

        ans = solution_data.get("final_answer", "")
        if ans:
            lines_to_draw.append("")
            lines_to_draw.append(f"∴ 정답: {ans}")

        tip = solution_data.get("tip", "")
        if tip:
            lines_to_draw.append("")
            wrapped_tip = self.engine.wrap_text(f"★ 핵심 Tip: {tip}", font_name, font_size, max_wrap_w)
            lines_to_draw.extend(wrapped_tip)

        # 전체 텍스트가 차지할 총 높이 계산
        total_text_h = len(lines_to_draw) * (font_size + line_spacing) + 80

        # 기존 이미지 하단의 잔여 공간 확인
        bottom_space = max(0, orig_h - max_y - 20)

        # 하단 공간이 전체 풀이 텍스트를 담기에 충분한지 확인
        if bottom_space >= total_text_h + 40:
            # 원본 이미지 내에 이미 충분한 여백이 있는 경우 (전체 시험지 등)
            working_img = base_img.convert("RGBA")
            start_x = max(int(orig_w * 0.07), min_x)
            start_y = max_y + 28
        else:
            # 문제 사진이 잘려 있거나 여백이 부족한 경우 (크롭 캡처 등)
            # 캔버스를 원본 아래로 확장하여 문제 본문을 100% 보존하고 아래에 완벽한 풀이 노트를 생성
            new_h = orig_h + total_text_h + 70
            bg_rgb = sample_background_color(base_img)
            
            working_img = Image.new("RGBA", (orig_w, new_h), bg_rgb + (255,))
            working_img.paste(base_img.convert("RGBA"), (0, 0))

            # 문제 본문과 손글씨 풀이 사이 깔끔하고 은은한 구분선 추가
            draw = ImageDraw.Draw(working_img)
            div_y = orig_h + 16
            draw.line([(int(orig_w * 0.05), div_y), (int(orig_w * 0.95), div_y)], fill=(210, 218, 228, 200), width=1)
            
            start_x = int(orig_w * 0.07)
            start_y = div_y + 36

        # 손글씨 렌더링
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
        문제 지문을 가리지 않도록 포스트잇 메모지를 합성합니다.
        문제가 꽉 차 있는 경우 캔버스를 확장하여 깔끔하게 부착합니다.
        """
        orig_w, orig_h = base_img.size
        min_x, min_y, max_x, max_y = detect_content_bounds(base_img)

        font_size = max(18, min(24, int(orig_w * 0.024)))
        line_spacing = int(font_size * 0.45)
        
        postit_w = max(380, min(650, int(orig_w * 0.85)))
        wrap_w = postit_w - 55

        lines_to_draw: List[str] = []
        title = solution_data.get("problem_title", "풀이 과정")
        lines_to_draw.append(f"[풀이] {title}")
        lines_to_draw.append("")

        for step in solution_data.get("steps", []):
            wrapped = self.engine.wrap_text(step, font_name, font_size, wrap_w)
            lines_to_draw.extend(wrapped)

        ans = solution_data.get("final_answer", "")
        if ans:
            lines_to_draw.append("")
            lines_to_draw.append(f"정답: {ans}")

        tip = solution_data.get("tip", "")
        if tip:
            lines_to_draw.append("")
            wrapped_tip = self.engine.wrap_text(f"Tip: {tip}", font_name, font_size, wrap_w)
            lines_to_draw.extend(wrapped_tip)

        tape_h = 30
        postit_h = max(320, len(lines_to_draw) * (font_size + line_spacing) + tape_h + 60)

        bg_rgb = POSTIT_COLORS.get(postit_color_name, (255, 250, 195))

        # 포스트잇 생성
        postit = Image.new("RGBA", (postit_w, postit_h), bg_rgb + (255,))
        draw = ImageDraw.Draw(postit)

        # 상단 테이프
        darker_color = (max(0, bg_rgb[0] - 15), max(0, bg_rgb[1] - 15), max(0, bg_rgb[2] - 15), 180)
        draw.rectangle([0, 0, postit_w, tape_h], fill=darker_color)

        postit_with_text, end_pos = self.engine.draw_handwritten_text(
            base_img=postit,
            text_lines=lines_to_draw,
            start_pos=(25, tape_h + 15),
            font_name=font_name,
            font_size=font_size,
            pen_style_name=pen_style,
            line_spacing=line_spacing,
            apply_jitter=True
        )

        # 그림자 및 약간의 기울기
        angle = random.uniform(-1.2, 1.2)
        pad = 25
        shadow_box = Image.new("RGBA", (postit_w + pad * 2, postit_h + pad * 2), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow_box)
        sdraw.rectangle([pad + 4, pad + 8, pad + postit_w + 4, pad + postit_h + 8], fill=(0, 0, 0, 60))
        shadow_box = shadow_box.filter(ImageFilter.GaussianBlur(8))

        shadow_box.alpha_composite(postit_with_text, (pad, pad))
        rotated_postit = shadow_box.rotate(angle, resample=Image.BICUBIC, expand=True)

        # 배치 영역 및 캔버스 확장 판별
        bottom_space = max(0, orig_h - max_y - 20)

        if bottom_space < rotated_postit.height + 40:
            new_h = orig_h + rotated_postit.height + 60
            bg_rgb_base = sample_background_color(base_img)
            result = Image.new("RGBA", (orig_w, new_h), bg_rgb_base + (255,))
            result.paste(base_img.convert("RGBA"), (0, 0))
            target_y = orig_h + 20
        else:
            result = base_img.convert("RGBA")
            target_y = max_y + 20

        target_x = max(15, int((orig_w - rotated_postit.width) / 2))
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
        풀이 길이에 맞춰 세로 높이도 지능적으로 조절합니다.
        """
        orig_w, orig_h = base_img.size
        ext_w = max(450, int(orig_w * 0.8))
        font_size = max(20, min(28, int(ext_w * 0.038)))
        line_spacing = int(font_size * 0.45)

        lines_to_draw = [
            "📝 [선생님 손글씨 풀이 노트]",
            "────────────────────────",
            f"문제: {solution_data.get('problem_title', '풀이')}",
            ""
        ]
        for step in solution_data.get("steps", []):
            wrapped = self.engine.wrap_text(step, font_name, font_size, ext_w - 65)
            lines_to_draw.extend(wrapped)

        ans = solution_data.get("final_answer", "")
        if ans:
            lines_to_draw.append("")
            lines_to_draw.append(f"★ 정답: {ans}")

        tip = solution_data.get("tip", "")
        if tip:
            lines_to_draw.append("")
            wrapped_tip = self.engine.wrap_text(f"Tip: {tip}", font_name, font_size, ext_w - 65)
            lines_to_draw.extend(wrapped_tip)

        total_text_h = len(lines_to_draw) * (font_size + line_spacing) + 120
        new_h = max(orig_h, total_text_h)
        new_w = orig_w + ext_w

        bg_rgb_base = sample_background_color(base_img)
        result = Image.new("RGBA", (new_w, new_h), bg_rgb_base + (255,))
        result.paste(base_img.convert("RGBA"), (0, 0))

        # 우측 그리드(모눈) 배경 생성
        grid_overlay = Image.new("RGBA", (ext_w, new_h), (252, 252, 252, 255))
        draw = ImageDraw.Draw(grid_overlay)
        grid_size = 24
        grid_color = (226, 232, 240, 255)
        for x in range(0, ext_w, grid_size):
            draw.line([(x, 0), (x, new_h)], fill=grid_color, width=1)
        for y in range(0, new_h, grid_size):
            draw.line([(0, y), (ext_w, y)], fill=grid_color, width=1)

        # 그림자 효과 (왼쪽 경계선)
        for i in range(12):
            alpha = int(45 * (1 - i / 12))
            draw.line([(i, 0), (i, new_h)], fill=(0, 0, 0, alpha), width=1)

        result.alpha_composite(grid_overlay, (orig_w, 0))

        result_with_text, end_pos = self.engine.draw_handwritten_text(
            base_img=result,
            text_lines=lines_to_draw,
            start_pos=(orig_w + 35, 40),
            font_name=font_name,
            font_size=font_size,
            pen_style_name=pen_style,
            line_spacing=line_spacing,
            apply_jitter=True
        )

        return result_with_text.convert("RGB")

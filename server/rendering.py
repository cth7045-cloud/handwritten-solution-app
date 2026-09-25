"""
업로드 이미지 전처리와 손글씨 합성 렌더링을 담당합니다.
AI 호출(느림)과 렌더링(빠름, ~100ms)을 분리해 두었기 때문에
폰트/펜/레이아웃만 바꿀 때는 AI를 다시 부르지 않고 즉시 다시 그릴 수 있습니다.
"""
import io
import random
import threading
from functools import lru_cache
from typing import Any, Dict

from PIL import Image, ImageOps

from core.handwriting_engine import HandwritingEngine
from core.overlay_composer import OverlayComposer

from .catalog import FONTS, PENS, POSTITS

# 스마트폰 원본 사진(4000px 이상)은 AI 전송과 합성 모두 느리게 만드므로 긴 변 기준으로 줄입니다.
MAX_IMAGE_SIDE = 1800
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

_engine = HandwritingEngine(fonts_dir="fonts")
_composer = OverlayComposer(_engine)
# 엔진이 전역 random 모듈을 쓰므로, seed 재현성을 위해 렌더링을 직렬화합니다(렌더 1회 ~100ms).
_render_lock = threading.Lock()


class InvalidImageError(ValueError):
    pass


def load_upload_image(data: bytes) -> Image.Image:
    """업로드 바이트를 검증하고, EXIF 회전을 바로잡고, 적정 크기로 줄인 RGB 이미지를 반환합니다."""
    if not data:
        raise InvalidImageError("이미지가 비어 있습니다.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise InvalidImageError("이미지가 너무 큽니다. (최대 15MB)")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:
        raise InvalidImageError("이미지 파일을 읽을 수 없습니다.") from e
    img = ImageOps.exif_transpose(img).convert("RGB")
    if max(img.size) > MAX_IMAGE_SIDE:
        img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.LANCZOS)
    return img


def image_to_jpeg_bytes(img: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def render_solution(
    base_img: Image.Image,
    solution: Dict[str, Any],
    font: str,
    pen: str,
    layout: str,
    postit_color: str = "yellow",
    seed: int = 0,
) -> bytes:
    """풀이 JSON을 선택한 스타일로 원본 이미지에 합성하고 PNG 바이트를 반환합니다."""
    font_name = FONTS[font]
    pen_style = PENS[pen]
    with _render_lock:
        random.seed(seed)
        if layout == "postit":
            out = _composer.compose_postit_mode(base_img, solution, font_name, pen_style, postit_color_name=POSTITS[postit_color])
        elif layout == "notebook":
            out = _composer.compose_notebook_extension_mode(base_img, solution, font_name, pen_style)
        else:
            out = _composer.compose_margin_mode(base_img, solution, font_name, pen_style)
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


@lru_cache(maxsize=256)
def font_preview_png(font: str, pen: str) -> bytes:
    """폰트 선택 카드에 쓰는 실제 필기 예시 이미지."""
    w, h = 360, 84
    card = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    with _render_lock:
        random.seed(f"{font}:{pen}")
        out, _ = _engine.draw_handwritten_text(
            base_img=card,
            text_lines=["f'(x) = 3x^2 - 6x  =>  극값", "∴ 정답: x = 2 (최솟값 -4)"],
            start_pos=(12, 12),
            font_name=FONTS[font],
            font_size=22,
            pen_style_name=PENS[pen],
            line_spacing=10,
            apply_jitter=True,
        )
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()

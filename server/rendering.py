"""
업로드 이미지 전처리와 손글씨 합성 렌더링을 담당합니다.
AI 호출(느림)과 렌더링(빠름, ~100ms)을 분리해 두었기 때문에
폰트/펜/레이아웃만 바꿀 때는 AI를 다시 부르지 않고 즉시 다시 그릴 수 있습니다.
"""
import io
import random
import threading
from functools import lru_cache
from typing import Any, Dict, List

from PIL import Image, ImageOps

from core.annotation_engine import FigureAnnotator
from core.handwriting_engine import HandwritingEngine
from core.overlay_composer import OverlayComposer
from core.page_layouts import A4_DPI, A4_W, PageComposer

from .catalog import FONTS, PENS, POSTITS

# 스마트폰 원본 사진(4000px 이상)은 AI 전송과 합성 모두 느리게 만드므로 긴 변 기준으로 줄입니다.
MAX_IMAGE_SIDE = 1800
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

_engine = HandwritingEngine(fonts_dir="fonts")
_composer = OverlayComposer(_engine)
_annotator = FigureAnnotator(_engine)
_pages = PageComposer(_composer)
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


def render_pages(
    base_img: Image.Image,
    solution: Dict[str, Any],
    font: str,
    pen: str,
    layout: str,
    postit_color: str = "yellow",
    seed: int = 0,
    marks: bool = True,
) -> List[Image.Image]:
    """풀이 JSON을 선택한 스타일로 합성해 페이지(그림) 목록을 돌려줍니다. A4 레포트만 여러 장이 될 수 있습니다.
    marks=True면 먼저 문제 그림 위에 길이·각·강조선·정답 체크 같은 표시를 그린 뒤 풀이를 붙입니다."""
    font_name = FONTS[font]
    pen_style = PENS[pen]
    with _render_lock:
        random.seed(seed)
        annotations = solution.get("figure_annotations") or []
        if marks and annotations:
            base_img = _annotator.annotate(base_img, annotations, font_name, pen_style)
        if layout == "report":
            return _pages.report_pages(base_img, solution, font_name, pen_style)
        if layout == "cornell":
            return [_pages.cornell(base_img, solution, font_name, pen_style)]
        if layout == "postit":
            out = _composer.compose_postit_mode(base_img, solution, font_name, pen_style, postit_color_name=POSTITS[postit_color])
        elif layout == "notebook":
            out = _composer.compose_notebook_extension_mode(base_img, solution, font_name, pen_style)
        else:
            out = _composer.compose_margin_mode(base_img, solution, font_name, pen_style)
    return [out]


def render_solution(*args, fmt: str = "png", **kwargs) -> bytes:
    """render_pages 결과를 PNG(여러 장이면 세로로 이어 붙임) 또는 PDF 바이트로 만듭니다."""
    pages = [p.convert("RGB") for p in render_pages(*args, **kwargs)]
    buf = io.BytesIO()
    if fmt == "pdf":
        # A4 레포트는 실제 A4 크기로, 나머지는 가로가 A4 폭(210mm)이 되도록 인쇄 해상도를 맞춥니다
        dpi = A4_DPI if pages[0].width == A4_W else max(72.0, pages[0].width / 8.27)
        pages[0].save(buf, format="PDF", save_all=True, append_images=pages[1:], resolution=dpi)
    else:
        PageComposer.stack_pages(pages).save(buf, format="PNG", optimize=False)
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

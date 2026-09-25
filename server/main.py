"""
AI 문제집 손글씨 해설 노트 생성기 - 웹 API 서버 (FastAPI)

  POST /api/solve   문제 이미지 -> 풀이 JSON        (AI 호출, 수 초 소요)
  POST /api/render  이미지 + 풀이 JSON + 스타일 -> PNG (AI 없이 ~100ms)
  GET  /api/styles  폰트/펜/레이아웃/포스트잇 목록
  GET  /api/fonts/{font}/preview.png?pen=...  폰트 미리보기 카드

실행: uvicorn server.main:app --reload
"""
import json
import os
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from core.gemini_solver import solve_problem_with_gemini

from .catalog import FONTS, LAYOUTS, PENS, POSTITS, SOLVE_MODES, catalog_payload
from .rendering import (
    InvalidImageError,
    font_preview_png,
    image_to_jpeg_bytes,
    load_upload_image,
    render_solution,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"

MAX_STEPS = 60
MAX_TEXT_LEN = 600

app = FastAPI(title="AI 손글씨 해설 노트 생성기", docs_url="/api/docs", openapi_url="/api/openapi.json")


def _read_image(data: bytes):
    try:
        return load_upload_image(data)
    except InvalidImageError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _clean_solution(raw: Dict[str, Any]) -> Dict[str, Any]:
    """AI 응답(또는 클라이언트가 돌려보낸 풀이)을 렌더링에 안전한 형태로 정리합니다."""
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="풀이 데이터 형식이 올바르지 않습니다.")

    def text(key: str) -> str:
        v = raw.get(key, "")
        return str(v)[:MAX_TEXT_LEN] if v is not None else ""

    steps = raw.get("steps") or []
    if not isinstance(steps, list):
        steps = [steps]
    diagram = raw.get("diagram") if isinstance(raw.get("diagram"), dict) else None
    return {
        "problem_title": text("problem_title"),
        "problem_summary": text("problem_summary"),
        "steps": [str(s)[:MAX_TEXT_LEN] for s in steps[:MAX_STEPS]],
        "final_answer": text("final_answer"),
        "tip": text("tip"),
        "has_diagram": bool(raw.get("has_diagram")) and diagram is not None,
        "diagram": diagram,
        "used_model": text("used_model"),
    }


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/styles")
def styles():
    return catalog_payload()


@app.get("/api/fonts/{font}/preview.png")
def font_preview(font: str, pen: str = "deepblue"):
    if font not in FONTS or pen not in PENS:
        raise HTTPException(status_code=404, detail="알 수 없는 폰트 또는 펜입니다.")
    return Response(
        content=font_preview_png(font, pen),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.post("/api/solve")
def solve(image: UploadFile = File(...), mode: str = Form("killer_tutor")):
    if mode not in SOLVE_MODES:
        raise HTTPException(status_code=422, detail="알 수 없는 풀이 방식입니다.")
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="서버에 GEMINI_API_KEY가 설정되지 않았습니다.")

    img = _read_image(image.file.read())
    started = time.monotonic()
    result = solve_problem_with_gemini(
        image_bytes=image_to_jpeg_bytes(img),
        mime_type="image/jpeg",
        api_key=api_key,
        solve_style=mode,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if not isinstance(result, dict) or result.get("error"):
        detail = result.get("error_message") if isinstance(result, dict) else None
        raise HTTPException(status_code=502, detail=f"AI 풀이 생성에 실패했습니다. {detail or ''}".strip())

    solution = _clean_solution(result)
    return JSONResponse({"solution": solution, "elapsed_ms": elapsed_ms})


@app.post("/api/render")
def render(
    image: UploadFile = File(...),
    solution: str = Form(...),
    font: str = Form("NanumAmsterdam"),
    pen: str = Form("deepblue"),
    layout: str = Form("margin"),
    postit_color: str = Form("yellow"),
    seed: int = Form(0),
):
    if font not in FONTS or pen not in PENS or layout not in LAYOUTS or postit_color not in POSTITS:
        raise HTTPException(status_code=422, detail="알 수 없는 스타일 옵션입니다.")
    try:
        parsed = json.loads(solution)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="풀이 데이터가 올바른 JSON이 아닙니다.")

    img = _read_image(image.file.read())
    png = render_solution(img, _clean_solution(parsed), font, pen, layout, postit_color, seed)
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})


# API 라우트보다 뒤에 마운트해야 /api/* 가 정적 파일에 가려지지 않습니다.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

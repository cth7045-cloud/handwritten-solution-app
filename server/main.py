"""
AI 문제집 손글씨 해설 노트 생성기 - 웹 API 서버 (FastAPI)

  POST /api/solve   문제 이미지 -> 풀이 JSON        (로그인 필요, 일일 한도 차감, 기록 저장)
  POST /api/render  이미지 + 풀이 JSON + 스타일 -> PNG (AI 없이 ~100ms)
                    또는 solve_id + 스타일 (저장된 기록을 다시 그리기)
  GET  /api/history 내 풀이 기록
  GET  /api/styles  폰트/펜/레이아웃/포스트잇 목록
  /api/auth/*, /api/admin/*  회원/관리자 (api_auth.py)

실행: uvicorn server.main:app --reload
"""
import io
import json
import logging
import os
import random
import time
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from core.annotation_engine import clean_annotations
from core.gemini_solver import solve_problem_with_gemini

from . import api_auth
from .accounts import Store
from .catalog import FONTS, LAYOUTS, PENS, POSTITS, SOLVE_MODES, catalog_payload
from .config import ROOT_DIR, Settings, load_settings
from .db import init_db, make_engine
from .rendering import (
    InvalidImageError,
    font_preview_png,
    image_to_jpeg_bytes,
    load_upload_image,
    render_solution,
)
from .security import LoginThrottle, SecurityMiddleware, current_user, get_store

logging.basicConfig(level=logging.INFO)

WEB_DIR = ROOT_DIR / "web"

MAX_STEPS = 60
MAX_TEXT_LEN = 600


def friendly_ai_error(detail: str) -> str:
    """구글 API의 긴 영문 오류를 사용자가 이해할 수 있는 안내로 바꿉니다 (자세한 내용은 서버 로그에)."""
    logging.getLogger("solve").warning("AI 풀이 실패: %s", detail[:500])
    if "RESOURCE_EXHAUSTED" in detail or "429" in detail:
        return "오늘 AI 무료 사용량을 모두 썼습니다. 내일 다시 이용하거나 관리자에게 문의해 주세요."
    if "UNAVAILABLE" in detail or "503" in detail or "high demand" in detail:
        return "지금 AI 사용자가 많아 응답하지 못했습니다. 잠시 후 다시 시도해 주세요."
    if "API key" in detail or "API_KEY" in detail or "PERMISSION_DENIED" in detail:
        return "서버의 AI 키 설정에 문제가 있습니다. 관리자에게 문의해 주세요."
    return "AI 풀이 생성에 실패했습니다. 잠시 후 다시 시도해 주세요."


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
        # AI가 그래프가 필요 없다고 했으면(has_diagram=false) 함께 온 diagram 은 버립니다
        "diagram": diagram if raw.get("has_diagram") else None,
        "used_model": text("used_model"),
        # 문제 그림 위에 직접 그릴 표시 (길이, 각, 강조선, 정답 체크 등)
        "figure_annotations": clean_annotations(raw.get("figure_annotations")),
    }


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or load_settings()
    engine = make_engine(settings.database_url)
    store = Store(engine, settings)
    # 워커 여러 개가 동시에 시작하면 테이블 생성/관리자 계정 생성이 겹칠 수 있어 몇 번 재시도합니다.
    for attempt in range(5):
        try:
            init_db(engine)
            store.ensure_admin()
            break
        except DBAPIError:
            if attempt == 4:
                raise
            time.sleep(0.5 + random.random())

    app = FastAPI(title="AI 손글씨 해설 노트 생성기", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.store = store
    app.state.login_throttle = LoginThrottle()
    app.add_middleware(SecurityMiddleware)
    app.include_router(api_auth.router)

    @app.get("/healthz")
    def healthz(store: Store = Depends(get_store)):
        # DB까지 한 번 두드려서, 주기적인 헬스체크가 서버와 DB(Supabase 무료 플랜 일시정지)를 함께 깨워 둡니다
        try:
            with store.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except DBAPIError:
            raise HTTPException(status_code=503, detail="데이터베이스에 연결할 수 없습니다.")
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
    def solve(
        image: UploadFile = File(...),
        mode: str = Form("killer_tutor"),
        user: dict = Depends(current_user),
        store: Store = Depends(get_store),
    ):
        if mode not in SOLVE_MODES:
            raise HTTPException(status_code=422, detail="알 수 없는 풀이 방식입니다.")
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise HTTPException(status_code=503, detail="서버에 GEMINI_API_KEY가 설정되지 않았습니다.")

        img = _read_image(image.file.read())
        if not store.reserve_solve(user):
            limit = store.effective_limit(user)
            raise HTTPException(status_code=429, detail=f"오늘 풀이 한도({limit}회)를 모두 사용했습니다. 내일 다시 이용해 주세요.")

        jpeg = image_to_jpeg_bytes(img)
        started = time.monotonic()
        try:
            result = solve_problem_with_gemini(
                image_bytes=jpeg,
                mime_type="image/jpeg",
                api_key=api_key,
                solve_style=mode,
            )
        except Exception as e:  # 예상 못 한 오류도 한도를 돌려줘야 합니다
            result = {"error": True, "error_message": str(e)}
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if not isinstance(result, dict) or result.get("error"):
            store.refund_solve(user["id"])
            detail = result.get("error_message") if isinstance(result, dict) else None
            raise HTTPException(status_code=502, detail=friendly_ai_error(detail or ""))

        solution = _clean_solution(result)
        solve_id = store.add_solve(user["id"], mode, solution, jpeg, elapsed_ms)
        return JSONResponse(
            {"solution": solution, "solve_id": solve_id, "elapsed_ms": elapsed_ms, "usage": store.usage_summary(user)}
        )

    @app.post("/api/render")
    def render(
        image: Optional[UploadFile] = File(None),
        solution: Optional[str] = Form(None),
        solve_id: Optional[int] = Form(None),
        font: str = Form("NanumAmsterdam"),
        pen: str = Form("deepblue"),
        layout: str = Form("margin"),
        postit_color: str = Form("yellow"),
        seed: int = Form(0),
        marks: bool = Form(True),
        user: dict = Depends(current_user),
        store: Store = Depends(get_store),
    ):
        if font not in FONTS or pen not in PENS or layout not in LAYOUTS or postit_color not in POSTITS:
            raise HTTPException(status_code=422, detail="알 수 없는 스타일 옵션입니다.")
        if solve_id is not None:
            record = store.get_solve(user["id"], solve_id)
            if not record:
                raise HTTPException(status_code=404, detail="풀이 기록을 찾을 수 없습니다.")
            img = _read_image(record["image"])
            parsed = record["solution"]
            store.save_solve_style(
                user["id"], solve_id, font=font, pen=pen, layout=layout, postit_color=postit_color, seed=seed
            )
        else:
            if image is None or solution is None:
                raise HTTPException(status_code=422, detail="이미지와 풀이 데이터 또는 solve_id가 필요합니다.")
            try:
                parsed = json.loads(solution)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail="풀이 데이터가 올바른 JSON이 아닙니다.")
            img = _read_image(image.file.read())
        png = render_solution(img, _clean_solution(parsed), font, pen, layout, postit_color, seed, marks)
        return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})

    # ---------- 풀이 기록 ----------
    @app.get("/api/history")
    def history(offset: int = 0, user: dict = Depends(current_user), store: Store = Depends(get_store)):
        return {"items": store.list_solves(user["id"], limit=30, offset=max(0, offset))}

    @app.get("/api/history/{solve_id}")
    def history_detail(solve_id: int, user: dict = Depends(current_user), store: Store = Depends(get_store)):
        record = store.get_solve(user["id"], solve_id)
        if not record:
            raise HTTPException(status_code=404, detail="풀이 기록을 찾을 수 없습니다.")
        record.pop("image")
        return record

    @app.get("/api/history/{solve_id}/image")
    def history_image(
        solve_id: int, thumb: bool = False, user: dict = Depends(current_user), store: Store = Depends(get_store)
    ):
        record = store.get_solve(user["id"], solve_id)
        if not record:
            raise HTTPException(status_code=404, detail="풀이 기록을 찾을 수 없습니다.")
        data = record["image"]
        if thumb:
            im = Image.open(io.BytesIO(data))
            im.thumbnail((320, 320))
            data = image_to_jpeg_bytes(im, quality=80)
        return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})

    @app.delete("/api/history/{solve_id}")
    def history_delete(solve_id: int, user: dict = Depends(current_user), store: Store = Depends(get_store)):
        if not store.delete_solve(user["id"], solve_id):
            raise HTTPException(status_code=404, detail="풀이 기록을 찾을 수 없습니다.")
        return {"ok": True}

    # API 라우트보다 뒤에 마운트해야 /api/* 가 정적 파일에 가려지지 않습니다.
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()

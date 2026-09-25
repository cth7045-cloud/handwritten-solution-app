"""
회원가입/로그인/로그아웃/비밀번호 변경과 관리자 API.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from .accounts import AccountError, Store, username_key
from .security import (
    SESSION_COOKIE,
    clear_session_cookie,
    client_ip,
    current_user,
    get_store,
    require_admin,
    set_session_cookie,
)

router = APIRouter(prefix="/api")


class Credentials(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class AdminUserUpdate(BaseModel):
    is_active: Optional[bool] = None
    daily_limit: Optional[int] = None
    use_default_limit: bool = False  # true면 daily_limit을 기본값(NULL)으로 되돌림
    new_password: Optional[str] = None


def _me_payload(store: Store, user: dict) -> dict:
    return {"user": user, "usage": store.usage_summary(user), "allow_signup": store.settings.allow_signup}


@router.get("/auth/config")
def auth_config(store: Store = Depends(get_store)):
    return {"allow_signup": store.settings.allow_signup}


@router.get("/auth/me")
def me(user: dict = Depends(current_user), store: Store = Depends(get_store)):
    return _me_payload(store, user)


@router.post("/auth/signup")
def signup(body: Credentials, request: Request, response: Response, store: Store = Depends(get_store)):
    if not store.settings.allow_signup:
        raise HTTPException(status_code=403, detail="현재 신규 가입을 받지 않습니다.")
    try:
        user = store.create_user(body.username, body.password)
    except AccountError as e:
        raise HTTPException(status_code=400, detail=str(e))
    set_session_cookie(request, response, store.create_session(user["id"]), store.settings.session_days)
    return _me_payload(store, user)


@router.post("/auth/login")
def login(body: Credentials, request: Request, response: Response, store: Store = Depends(get_store)):
    throttle = request.app.state.login_throttle
    ip, key = client_ip(request), username_key(body.username)
    wait = throttle.retry_after(ip, key)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"로그인 시도가 너무 많습니다. {wait // 60 + 1}분 후 다시 시도해 주세요.",
            headers={"Retry-After": str(wait)},
        )
    try:
        user = store.authenticate(body.username, body.password)
    except AccountError as e:
        throttle.failed(ip, key)
        raise HTTPException(status_code=401, detail=str(e))
    throttle.succeeded(ip, key)
    set_session_cookie(request, response, store.create_session(user["id"]), store.settings.session_days)
    return _me_payload(store, user)


@router.post("/auth/logout")
def logout(request: Request, response: Response, store: Store = Depends(get_store)):
    store.revoke_session(request.cookies.get(SESSION_COOKIE))
    clear_session_cookie(response)
    return {"ok": True}


@router.post("/auth/password")
def change_password(
    body: PasswordChange,
    request: Request,
    response: Response,
    user: dict = Depends(current_user),
    store: Store = Depends(get_store),
):
    try:
        store.change_password(user["id"], body.current_password, body.new_password)
    except AccountError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 비밀번호 변경 시 모든 기기에서 로그아웃되므로, 지금 기기에는 새 세션을 발급
    set_session_cookie(request, response, store.create_session(user["id"]), store.settings.session_days)
    return {"ok": True}


# ---------- 관리자 ----------
@router.get("/admin/stats")
def admin_stats(_: dict = Depends(require_admin), store: Store = Depends(get_store)):
    return {**store.stats(), "default_daily_limit": store.settings.daily_solve_limit}


@router.get("/admin/users")
def admin_users(_: dict = Depends(require_admin), store: Store = Depends(get_store)):
    return {"users": store.list_users()}


@router.patch("/admin/users/{user_id}")
def admin_update_user(
    user_id: int,
    body: AdminUserUpdate,
    admin: dict = Depends(require_admin),
    store: Store = Depends(get_store),
):
    kwargs = {"is_active": body.is_active, "new_password": body.new_password or None}
    if body.use_default_limit:
        kwargs["daily_limit"] = None
    elif body.daily_limit is not None:
        kwargs["daily_limit"] = body.daily_limit
    try:
        return {"user": store.admin_update_user(admin["id"], user_id, **kwargs)}
    except AccountError as e:
        raise HTTPException(status_code=400, detail=str(e))

"""
로그인 세션 쿠키, 로그인 시도 제한, 교차 출처 요청 차단, 보안 헤더.
"""
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .accounts import Store

SESSION_COOKIE = "hw_session"

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' https://cdn.jsdelivr.net; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "img-src 'self' blob: data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def get_store(request: Request) -> Store:
    return request.app.state.store


def set_session_cookie(request: Request, response: Response, token: str, days: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=days * 86400,
        httponly=True,  # JS에서 읽을 수 없게 (XSS로 세션 탈취 방지)
        samesite="lax",  # 다른 사이트에서 보낸 POST에는 쿠키가 실리지 않음 (CSRF 방지)
        secure=request.url.scheme == "https",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def current_user(request: Request, store: Store = Depends(get_store)) -> dict:
    user = store.user_for_session(request.cookies.get(SESSION_COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="관리자만 이용할 수 있습니다.")
    return user


def client_ip(request: Request) -> str:
    # Cloud Run 등 프록시 뒤에서는 X-Forwarded-For의 첫 번째 값이 실제 접속 IP
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class LoginThrottle:
    """같은 IP+아이디로 10분 안에 5번 틀리면 잠시 로그인을 막습니다 (무차별 대입 방지).
    서버 인스턴스별 메모리에 기록하므로, 인스턴스가 여러 대면 대당 기준으로 적용됩니다."""

    def __init__(self, max_failures: int = 5, window_sec: int = 600):
        self.max_failures = max_failures
        self.window = window_sec
        self._fails: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key, now: float) -> Deque[float]:
        q = self._fails[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def retry_after(self, ip: str, username: str) -> Optional[int]:
        now = time.monotonic()
        with self._lock:
            q = self._prune((ip, username), now)
            if len(q) >= self.max_failures:
                return int(self.window - (now - q[0])) + 1
        return None

    def failed(self, ip: str, username: str) -> None:
        with self._lock:
            self._fails[(ip, username)].append(time.monotonic())

    def succeeded(self, ip: str, username: str) -> None:
        with self._lock:
            self._fails.pop((ip, username), None)


class SecurityMiddleware(BaseHTTPMiddleware):
    """다른 사이트에서 보낸 상태 변경 요청을 막고, 기본 보안 헤더를 붙입니다."""

    async def dispatch(self, request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "허용되지 않은 요청 출처입니다."}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Content-Security-Policy", CSP)
        if request.url.path.startswith("/api/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

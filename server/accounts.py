"""
회원, 로그인 세션, 일일 사용량, 풀이 기록을 다루는 저장소 계층 (FastAPI와 독립).
"""
import hashlib
import hmac
import json
import logging
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Engine

from .config import Settings
from .db import as_utc, daily_usage, sessions, solves, users, utcnow

log = logging.getLogger("accounts")

KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 오프셋으로 충분
PBKDF2_ITERATIONS = 600_000
USERNAME_RE = re.compile(r"^[0-9A-Za-z가-힣_.\-]{2,20}$")
MIN_PASSWORD_LEN = 8


class AccountError(ValueError):
    """사용자에게 그대로 보여줄 수 있는 오류 메시지."""


# ---------- 비밀번호 ----------
def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode(), int(iterations)).hex()
        return hmac.compare_digest(calc, digest)
    except (ValueError, AttributeError):
        return False


def normalize_username(username: str) -> str:
    # macOS 등에서 한글이 자모 분리(NFD)로 들어와도 같은 아이디로 인식되도록 NFC로 정규화
    return unicodedata.normalize("NFC", (username or "").strip())


def username_key(username: str) -> str:
    return normalize_username(username).casefold()


def validate_new_credentials(username: str, password: str) -> None:
    if not USERNAME_RE.match(normalize_username(username)):
        raise AccountError("아이디는 2~20자의 한글, 영문, 숫자, _ . - 만 사용할 수 있습니다.")
    validate_password(password)


def validate_password(password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise AccountError(f"비밀번호는 {MIN_PASSWORD_LEN}자 이상이어야 합니다.")
    if len(password) > 128:
        raise AccountError("비밀번호가 너무 깁니다.")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _public_user(row) -> Dict[str, Any]:
    return {
        "id": row.id,
        "username": row.username,
        "role": row.role,
        "is_active": bool(row.is_active),
        "daily_limit": row.daily_limit,
        "solve_count": row.solve_count,
        "created_at": as_utc(row.created_at).isoformat(),
        "last_login_at": as_utc(row.last_login_at).isoformat() if row.last_login_at else None,
    }


class Store:
    def __init__(self, engine: Engine, settings: Settings):
        self.engine = engine
        self.settings = settings

    # ---------- 회원 ----------
    def create_user(self, username: str, password: str, role: str = "user") -> Dict[str, Any]:
        validate_new_credentials(username, password)
        name = normalize_username(username)
        with self.engine.begin() as conn:
            if conn.execute(select(users.c.id).where(users.c.username_key == username_key(name))).first():
                raise AccountError("이미 사용 중인 아이디입니다.")
            uid = conn.execute(
                insert(users).values(
                    username=name,
                    username_key=username_key(name),
                    password_hash=hash_password(password),
                    role=role,
                    is_active=True,
                    solve_count=0,
                    created_at=utcnow(),
                )
            ).inserted_primary_key[0]
        return self.get_user(uid)

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as conn:
            row = conn.execute(select(users).where(users.c.id == user_id)).first()
        return _public_user(row) if row else None

    def ensure_admin(self) -> None:
        """ADMIN_USERNAME / ADMIN_PASSWORD 환경변수로 관리자 계정을 만들거나 비밀번호를 맞춥니다."""
        name, password = self.settings.admin_username, self.settings.admin_password
        if not name or not password:
            log.warning("ADMIN_PASSWORD가 설정되지 않아 관리자 계정을 만들지 않았습니다.")
            return
        with self.engine.begin() as conn:
            row = conn.execute(select(users).where(users.c.username_key == username_key(name))).first()
            if not row:
                conn.execute(
                    insert(users).values(
                        username=normalize_username(name),
                        username_key=username_key(name),
                        password_hash=hash_password(password),
                        role="admin",
                        is_active=True,
                        solve_count=0,
                        created_at=utcnow(),
                    )
                )
                log.info("관리자 계정 생성: %s", name)
                return
            values: Dict[str, Any] = {"role": "admin", "is_active": True}
            if not verify_password(password, row.password_hash):
                # 환경변수가 관리자 비밀번호의 기준입니다. 바뀌었으면 갱신하고 기존 로그인은 모두 끊습니다.
                values["password_hash"] = hash_password(password)
                conn.execute(delete(sessions).where(sessions.c.user_id == row.id))
                log.info("관리자 비밀번호를 환경변수 값으로 갱신: %s", name)
            conn.execute(update(users).where(users.c.id == row.id).values(**values))

    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        with self.engine.connect() as conn:
            row = conn.execute(select(users).where(users.c.username_key == username_key(username))).first()
        # 존재하지 않는 아이디/틀린 비밀번호를 구분하지 않아 아이디 수집을 어렵게 합니다
        if not row or not verify_password(password or "", row.password_hash):
            raise AccountError("아이디 또는 비밀번호가 올바르지 않습니다.")
        if not row.is_active:
            raise AccountError("관리자에 의해 이용이 정지된 계정입니다.")
        with self.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == row.id).values(last_login_at=utcnow()))
        return _public_user(row)

    def change_password(self, user_id: int, current: str, new: str) -> None:
        user = self.get_user(user_id)
        if user and user["role"] == "admin":
            raise AccountError("관리자 비밀번호는 서버의 ADMIN_PASSWORD 설정으로 변경합니다.")
        with self.engine.connect() as conn:
            row = conn.execute(select(users.c.password_hash).where(users.c.id == user_id)).first()
        if not row or not verify_password(current or "", row.password_hash):
            raise AccountError("현재 비밀번호가 올바르지 않습니다.")
        validate_password(new)
        self._set_password(user_id, new)

    def _set_password(self, user_id: int, new: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == user_id).values(password_hash=hash_password(new)))
            conn.execute(delete(sessions).where(sessions.c.user_id == user_id))

    # ---------- 세션 ----------
    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = utcnow()
        with self.engine.begin() as conn:
            conn.execute(delete(sessions).where(sessions.c.expires_at < now))
            conn.execute(
                insert(sessions).values(
                    token_hash=_token_hash(token),
                    user_id=user_id,
                    created_at=now,
                    expires_at=now + timedelta(days=self.settings.session_days),
                )
            )
        return token

    def user_for_session(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        with self.engine.connect() as conn:
            row = conn.execute(
                select(users, sessions.c.expires_at)
                .join(sessions, sessions.c.user_id == users.c.id)
                .where(sessions.c.token_hash == _token_hash(token))
            ).first()
        if not row or not row.is_active or as_utc(row.expires_at) < utcnow():
            return None
        return _public_user(row)

    def revoke_session(self, token: Optional[str]) -> None:
        if token:
            with self.engine.begin() as conn:
                conn.execute(delete(sessions).where(sessions.c.token_hash == _token_hash(token)))

    # ---------- 일일 사용량 ----------
    def effective_limit(self, user: Dict[str, Any]) -> Optional[int]:
        """None이면 무제한(관리자)."""
        if user["role"] == "admin":
            return None
        return user["daily_limit"] if user["daily_limit"] is not None else self.settings.daily_solve_limit

    def usage_today(self, user_id: int) -> int:
        with self.engine.connect() as conn:
            v = conn.execute(
                select(daily_usage.c.count).where(daily_usage.c.user_id == user_id, daily_usage.c.day == today_kst())
            ).scalar()
        return v or 0

    def usage_summary(self, user: Dict[str, Any]) -> Dict[str, Any]:
        return {"used": self.usage_today(user["id"]), "limit": self.effective_limit(user)}

    def _upsert_ignore(self, table, **values):
        dialect = self.engine.dialect.name
        mod = postgresql if dialect == "postgresql" else sqlite
        return mod.insert(table).values(**values).on_conflict_do_nothing()

    def reserve_solve(self, user: Dict[str, Any]) -> bool:
        """오늘 사용량을 1 올립니다. 한도를 넘으면 False. 동시 요청에도 한도를 넘지 않도록 조건부 UPDATE를 씁니다."""
        day = today_kst()
        limit = self.effective_limit(user)
        with self.engine.begin() as conn:
            conn.execute(self._upsert_ignore(daily_usage, user_id=user["id"], day=day, count=0))
            stmt = update(daily_usage).where(daily_usage.c.user_id == user["id"], daily_usage.c.day == day)
            if limit is not None:
                stmt = stmt.where(daily_usage.c.count < limit)
            return conn.execute(stmt.values(count=daily_usage.c.count + 1)).rowcount == 1

    def refund_solve(self, user_id: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(daily_usage)
                .where(daily_usage.c.user_id == user_id, daily_usage.c.day == today_kst(), daily_usage.c.count > 0)
                .values(count=daily_usage.c.count - 1)
            )

    # ---------- 풀이 기록 ----------
    def add_solve(self, user_id: int, mode: str, solution: Dict[str, Any], image: bytes, elapsed_ms: int) -> int:
        with self.engine.begin() as conn:
            sid = conn.execute(
                insert(solves).values(
                    user_id=user_id,
                    created_at=utcnow(),
                    mode=mode,
                    title=(solution.get("problem_title") or "")[:200],
                    final_answer=(solution.get("final_answer") or "")[:200],
                    solution_json=json.dumps(solution, ensure_ascii=False),
                    image=image,
                    elapsed_ms=elapsed_ms,
                )
            ).inserted_primary_key[0]
            conn.execute(update(users).where(users.c.id == user_id).values(solve_count=users.c.solve_count + 1))
            # 사용자별 최근 N개만 보관 (DB 용량 관리)
            keep = (
                select(solves.c.id)
                .where(solves.c.user_id == user_id)
                .order_by(solves.c.id.desc())
                .limit(self.settings.history_limit)
                .scalar_subquery()
            )
            conn.execute(delete(solves).where(solves.c.user_id == user_id, solves.c.id.not_in(keep)))
        return sid

    def list_solves(self, user_id: int, limit: int = 30, offset: int = 0) -> List[Dict[str, Any]]:
        cols = [solves.c.id, solves.c.created_at, solves.c.mode, solves.c.title, solves.c.final_answer]
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(*cols).where(solves.c.user_id == user_id).order_by(solves.c.id.desc()).limit(limit).offset(offset)
            ).all()
        return [
            {"id": r.id, "created_at": as_utc(r.created_at).isoformat(), "mode": r.mode, "title": r.title, "final_answer": r.final_answer}
            for r in rows
        ]

    def get_solve(self, user_id: int, solve_id: int) -> Optional[Dict[str, Any]]:
        with self.engine.connect() as conn:
            r = conn.execute(select(solves).where(solves.c.id == solve_id, solves.c.user_id == user_id)).first()
        if not r:
            return None
        return {
            "id": r.id,
            "created_at": as_utc(r.created_at).isoformat(),
            "mode": r.mode,
            "solution": json.loads(r.solution_json),
            "image": r.image,
            "elapsed_ms": r.elapsed_ms,
            "style": {"font": r.font, "pen": r.pen, "layout": r.layout, "postit_color": r.postit_color, "seed": r.seed},
        }

    def save_solve_style(self, user_id: int, solve_id: int, **style) -> None:
        with self.engine.begin() as conn:
            conn.execute(update(solves).where(solves.c.id == solve_id, solves.c.user_id == user_id).values(**style))

    def delete_solve(self, user_id: int, solve_id: int) -> bool:
        with self.engine.begin() as conn:
            return conn.execute(delete(solves).where(solves.c.id == solve_id, solves.c.user_id == user_id)).rowcount == 1

    # ---------- 관리자 ----------
    def list_users(self) -> List[Dict[str, Any]]:
        day = today_kst()
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(users, func.coalesce(daily_usage.c.count, 0).label("today"))
                .outerjoin(daily_usage, (daily_usage.c.user_id == users.c.id) & (daily_usage.c.day == day))
                .order_by(users.c.id)
            ).all()
        out = []
        for r in rows:
            u = _public_user(r)
            u["used_today"] = r.today
            u["effective_limit"] = self.effective_limit(u)
            out.append(u)
        return out

    def admin_update_user(
        self,
        admin_id: int,
        user_id: int,
        *,
        is_active: Optional[bool] = None,
        daily_limit: Any = ...,
        new_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        target = self.get_user(user_id)
        if not target:
            raise AccountError("존재하지 않는 회원입니다.")
        if target["role"] == "admin" or user_id == admin_id:
            raise AccountError("관리자 계정은 여기서 변경할 수 없습니다.")
        values: Dict[str, Any] = {}
        if is_active is not None:
            values["is_active"] = bool(is_active)
        if daily_limit is not ...:
            if daily_limit is not None and (not isinstance(daily_limit, int) or daily_limit < 0 or daily_limit > 10000):
                raise AccountError("일일 한도는 0~10000 사이의 숫자여야 합니다.")
            values["daily_limit"] = daily_limit
        with self.engine.begin() as conn:
            if values:
                conn.execute(update(users).where(users.c.id == user_id).values(**values))
            if values.get("is_active") is False:
                conn.execute(delete(sessions).where(sessions.c.user_id == user_id))
        if new_password:
            validate_password(new_password)
            self._set_password(user_id, new_password)
        return self.get_user(user_id)

    def stats(self) -> Dict[str, Any]:
        with self.engine.connect() as conn:
            total_users = conn.execute(select(func.count()).select_from(users)).scalar() or 0
            total_solves = conn.execute(select(func.coalesce(func.sum(users.c.solve_count), 0))).scalar() or 0
            today = conn.execute(
                select(func.coalesce(func.sum(daily_usage.c.count), 0)).where(daily_usage.c.day == today_kst())
            ).scalar() or 0
        return {"total_users": total_users, "total_solves": int(total_solves), "solves_today": int(today)}

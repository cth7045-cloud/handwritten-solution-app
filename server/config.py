"""
환경변수 기반 설정. 비밀값(API 키, 관리자 비밀번호, DB 주소)은 코드/저장소에 두지 않고
배포 환경의 Secret으로 주입합니다.
"""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    database_url: str
    admin_username: str
    admin_password: str
    allow_signup: bool
    daily_solve_limit: int
    history_limit: int
    session_days: int


def load_settings() -> Settings:
    default_db = f"sqlite:///{ROOT_DIR / 'data' / 'app.db'}"
    return Settings(
        database_url=os.environ.get("DATABASE_URL", "").strip() or default_db,
        admin_username=os.environ.get("ADMIN_USERNAME", "갈빙").strip(),
        admin_password=os.environ.get("ADMIN_PASSWORD", ""),
        allow_signup=_bool("ALLOW_SIGNUP", True),
        daily_solve_limit=_int("DAILY_SOLVE_LIMIT", 20),
        history_limit=_int("HISTORY_LIMIT", 100),
        session_days=_int("SESSION_DAYS", 365),
    )

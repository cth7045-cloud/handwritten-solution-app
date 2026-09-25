"""
데이터베이스 스키마와 연결.
로컬 개발은 SQLite(data/app.db), 배포는 DATABASE_URL로 PostgreSQL(Neon, Supabase, Cloud SQL 등)을 씁니다.
Cloud Run 같은 컨테이너는 재시작 시 로컬 파일이 사라지므로 배포 환경에서는 반드시 외부 DB를 지정하세요.
"""
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(40), nullable=False),
    # 대소문자/유니코드 정규화한 로그인 키 (중복 가입 방지)
    Column("username_key", String(40), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("role", String(16), nullable=False, default="user"),
    Column("is_active", Boolean, nullable=False, default=True),
    # NULL이면 기본 한도(DAILY_SOLVE_LIMIT)를 따릅니다
    Column("daily_limit", Integer, nullable=True),
    Column("solve_count", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_login_at", DateTime(timezone=True), nullable=True),
)

sessions = Table(
    "sessions",
    metadata,
    # 쿠키 토큰 원문이 아니라 SHA-256 해시만 저장합니다 (DB 유출 시 세션 탈취 방지)
    Column("token_hash", String(64), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)

daily_usage = Table(
    "daily_usage",
    metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("day", String(10), primary_key=True),  # 한국 시간 기준 YYYY-MM-DD
    Column("count", Integer, nullable=False, default=0),
)

solves = Table(
    "solves",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("mode", String(32), nullable=False),
    Column("title", String(200), nullable=False, default=""),
    Column("final_answer", String(200), nullable=False, default=""),
    Column("solution_json", Text, nullable=False),
    Column("image", LargeBinary, nullable=False),
    Column("elapsed_ms", Integer, nullable=False, default=0),
    # 마지막으로 선택한 스타일 (기록을 다시 열면 그대로 복원)
    Column("font", String(64), nullable=True),
    Column("pen", String(32), nullable=True),
    Column("layout", String(32), nullable=True),
    Column("postit_color", String(32), nullable=True),
    Column("seed", Integer, nullable=True),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """SQLite는 tz 정보를 버리므로 읽은 값을 UTC로 되돌립니다."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def make_engine(url: str) -> Engine:
    if url.startswith("postgres://"):  # Heroku/Neon 스타일 주소 호환
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("sqlite:///"):
        Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    # pool_pre_ping: 서버리스 Postgres가 유휴 연결을 끊어도 자동 재연결
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=300)


def init_db(engine: Engine) -> None:
    metadata.create_all(engine)

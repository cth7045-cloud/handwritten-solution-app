import os
import tempfile
import uuid

# server.main 은 import 시점에 기본 앱을 만들므로, 저장소의 data/ 를 건드리지 않도록 먼저 임시 DB를 지정합니다.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/import.db")
os.environ.pop("ADMIN_PASSWORD", None)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from server.config import Settings
from server.main import create_app

ADMIN = ("갈빙", "admin-test-pw")


def make_settings(db_url: str, **overrides) -> Settings:
    base = dict(
        database_url=db_url,
        admin_username=ADMIN[0],
        admin_password=ADMIN[1],
        allow_signup=True,
        daily_solve_limit=3,
        history_limit=100,
        session_days=365,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def db_url(tmp_path):
    """기본은 SQLite. TEST_DATABASE_URL(PostgreSQL)이 있으면 테스트마다 새 스키마를 만들어 실제 운영 DB로 검증합니다."""
    pg = os.environ.get("TEST_DATABASE_URL")
    if not pg:
        yield f"sqlite:///{tmp_path}/test.db"
        return
    schema = f"t_{uuid.uuid4().hex[:10]}"
    admin_engine = create_engine(pg.replace("postgresql://", "postgresql+psycopg://", 1))
    with admin_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    sep = "&" if "?" in pg else "?"
    yield f"{pg}{sep}options=-csearch_path%3D{schema}"
    with admin_engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin_engine.dispose()


@pytest.fixture
def make_client(db_url):
    def factory(**overrides):
        return TestClient(create_app(make_settings(db_url, **overrides)))
    return factory


@pytest.fixture
def client(make_client):
    return make_client()


def signup(client, username="학생1", password="password123"):
    res = client.post("/api/auth/signup", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})

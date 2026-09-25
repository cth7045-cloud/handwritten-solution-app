"""
회원가입, 로그인, 세션 및 관리자 기능을 관리하는 SQLite 기반 인증 매니저
"""
import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "auth.db")

def get_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """비밀번호를 PBKDF2-HMAC-SHA256으로 안전하게 단방향 암호화합니다."""
    if not salt:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return pw_hash, salt

def verify_password(password: str, pw_hash: str, salt: str) -> bool:
    new_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(new_hash, pw_hash)

def init_db():
    """데이터베이스 및 테이블을 생성하고 기본 관리자 계정을 설정합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. 사용자 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        is_active INTEGER NOT NULL DEFAULT 1,
        solve_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)
    
    # 2. 시스템 설정 테이블 (관리자 전용 공용 API 키 등)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    
    # 3. users 테이블 api_key 컬럼 마이그레이션
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN api_key TEXT DEFAULT ''")
    except Exception:
        pass

    # 4. 사용자 세션 테이블 (로그인 상태 유지용 영구 토큰)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_sessions (
        token TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    try:
        # 기존 세션도 기한 제한 없이 영구 유지(9999년)로 일괄 마이그레이션
        cursor.execute("UPDATE user_sessions SET expires_at = '9999-12-31 23:59:59' WHERE expires_at < '9000-01-01'")
    except Exception:
        pass

    conn.commit()
    
    # 3. 최고 관리자 계정 생성 및 암호화 설정
    # 비밀번호는 저장소에 두지 않고 ADMIN_PASSWORD 환경변수(또는 Streamlit secrets)로 받습니다.
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    admin_user = os.environ.get("ADMIN_USERNAME", "갈빙")
    admin_pw = os.environ.get("ADMIN_PASSWORD", "")
    if not admin_pw:
        try:
            import streamlit as st
            admin_pw = st.secrets.get("ADMIN_PASSWORD", "")
        except Exception:
            admin_pw = ""
    if not admin_pw:
        print("[!] ADMIN_PASSWORD가 설정되지 않아 관리자 계정을 만들거나 갱신하지 않았습니다.")
        conn.close()
        return
    pw_hash, salt = hash_password(admin_pw)

    cursor.execute("SELECT id FROM users WHERE username = ?", (admin_user,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("""
        INSERT INTO users (username, password_hash, salt, role, is_active, solve_count, created_at)
        VALUES (?, ?, ?, 'admin', 1, 0, ?)
        """, (admin_user, pw_hash, salt, now))
    else:
        cursor.execute("""
        UPDATE users SET password_hash = ?, salt = ?, role = 'admin', is_active = 1 WHERE username = ?
        """, (pw_hash, salt, admin_user))

    # 이전 임시 계정 정리
    cursor.execute("DELETE FROM users WHERE username IN ('cth7045', 'admin')")
            
    conn.commit()
    conn.close()

def register_user(username: str, password: str, role: str = "user") -> Tuple[bool, str]:
    """신규 회원가입"""
    username = username.strip()
    if not username or len(username) < 2:
        return False, "아이디는 최소 2자 이상이어야 합니다."
    if not password or len(password) < 4:
        return False, "비밀번호는 최소 4자 이상이어야 합니다."
        
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return False, "이미 존재하는 아이디입니다."
        
    pw_hash, salt = hash_password(password)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
    INSERT INTO users (username, password_hash, salt, role, is_active, solve_count, created_at)
    VALUES (?, ?, ?, ?, 1, 0, ?)
    """, (username, pw_hash, salt, role, now))
    
    conn.commit()
    conn.close()
    return True, "회원가입이 완료되었습니다! 로그인해주세요."

def authenticate_user(username: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """사용자 로그인 인증"""
    username = username.strip()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return False, None, "존재하지 않는 아이디입니다."
        
    if not row["is_active"]:
        return False, None, "관리자에 의해 비활성화된 계정입니다."
        
    if not verify_password(password, row["password_hash"], row["salt"]):
        return False, None, "비밀번호가 일치하지 않습니다."
        
    user_dict = {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "solve_count": row["solve_count"],
        "created_at": row["created_at"]
    }
    return True, user_dict, "로그인 성공!"

def increment_solve_count(username: str):
    """문제 풀이 횟수 누적"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET solve_count = solve_count + 1 WHERE username = ?", (username,))
    conn.commit()
    conn.close()

def get_all_users() -> List[Dict[str, Any]]:
    """모든 회원 목록 조회 (관리자 전용)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, is_active, solve_count, created_at FROM users ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_user_status(username: str, is_active: bool) -> bool:
    """회원 활성화/정지 변경 (관리자 전용)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_active = ? WHERE username = ?", (1 if is_active else 0, username))
    conn.commit()
    conn.close()
    return True

def change_password(username: str, new_password: str) -> Tuple[bool, str]:
    """비밀번호 변경"""
    if len(new_password) < 4:
        return False, "비밀번호는 최소 4자 이상이어야 합니다."
    pw_hash, salt = hash_password(new_password)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password_hash = ?, salt = ? WHERE username = ?", (pw_hash, salt, username))
    cursor.execute("DELETE FROM user_sessions WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return True, "비밀번호가 성공적으로 변경되었습니다. 모든 기기에서 다시 로그인해주세요."

def set_system_setting(key: str, value: str):
    """관리자 전용 전역 설정 저장 (예: 공용 API 키)"""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO system_settings (key, value, updated_at) VALUES (?, ?, ?)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
    """, (key, value, now))
    conn.commit()
    conn.close()

def get_system_setting(key: str, default: str = "") -> str:
    """시스템 설정 조회"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def save_user_api_key(username: str, api_key: str):
    """사용자의 Gemini API 키를 계정별로 영구 저장합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET api_key = ? WHERE username = ?", (api_key.strip(), username))
    conn.commit()
    conn.close()

def get_user_api_key(username: str) -> str:
    """사용자의 저장된 Gemini API 키를 조회합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT api_key FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row and "api_key" in row.keys() and row["api_key"]:
        return row["api_key"]
    return ""

def create_session(username: str, days: Optional[int] = None) -> str:
    """새로운 로그인 세션 토큰을 생성하고 DB에 영구 보존합니다 (기간 제한 없음)."""
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    if days is not None:
        expires_at = (now + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    else:
        expires_at = "9999-12-31 23:59:59"  # 만료 제한 없는 영구 세션
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    
    conn = get_connection()
    cursor = conn.cursor()
    # 만료된 세션 자동 정리 (영구 세션은 만료되지 않으므로 삭제되지 않음)
    cursor.execute("DELETE FROM user_sessions WHERE expires_at < ?", (now_str,))
    cursor.execute("""
    INSERT INTO user_sessions (token, username, expires_at, created_at)
    VALUES (?, ?, ?, ?)
    """, (token, username, expires_at, now_str))
    conn.commit()
    conn.close()
    return token

def validate_session(token: str) -> Optional[Dict[str, Any]]:
    """세션 토큰의 유효성을 검증하고 유효한 경우 사용자 정보를 즉시 반환합니다."""
    if not token or not isinstance(token, str):
        return None
    token = token.strip()
    if not token:
        return None
        
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT s.username, u.id, u.role, u.is_active, u.solve_count, u.created_at
    FROM user_sessions s
    JOIN users u ON s.username = u.username
    WHERE s.token = ? AND s.expires_at > ? AND u.is_active = 1
    """, (token, now_str))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "solve_count": row["solve_count"],
            "created_at": row["created_at"]
        }
    return None

def revoke_session(token: str):
    """지정된 세션 토큰을 DB에서 삭제(무효화)합니다."""
    if not token:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_sessions WHERE token = ?", (token.strip(),))
    conn.commit()
    conn.close()

def revoke_all_user_sessions(username: str):
    """사용자의 모든 활성 세션을 삭제합니다."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_sessions WHERE username = ?", (username,))
    conn.commit()
    conn.close()

# 초기화 실행
init_db()

"""
회원가입, 로그인, 세션 및 관리자 기능을 관리하는 SQLite 기반 인증 매니저
"""
import os
import sqlite3
import hashlib
import secrets
from datetime import datetime
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
    
    conn.commit()
    
    # 3. 기본 관리자 계정 생성 (cth7045 및 admin)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for admin_user in ["cth7045", "admin"]:
        cursor.execute("SELECT id FROM users WHERE username = ?", (admin_user,))
        if not cursor.fetchone():
            pw_hash, salt = hash_password("admin1234")
            cursor.execute("""
            INSERT INTO users (username, password_hash, salt, role, is_active, solve_count, created_at)
            VALUES (?, ?, ?, 'admin', 1, 0, ?)
            """, (admin_user, pw_hash, salt, now))
            print(f"[*] 기본 관리자 계정 생성 완료: {admin_user}")
            
    conn.commit()
    conn.close()

def register_user(username: str, password: str, role: str = "user") -> Tuple[bool, str]:
    """신규 회원가입"""
    username = username.strip()
    if not username or len(username) < 3:
        return False, "아이디는 최소 3자 이상이어야 합니다."
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
    conn.commit()
    conn.close()
    return True, "비밀번호가 성공적으로 변경되었습니다."

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

# 초기화 실행
init_db()

"""
문제집 손글씨 풀이 합성 웹 애플리케이션 (ScribeNote AI)
Streamlit 기반 정식 상용 SaaS 스타일 리모델링 UI
"""
import os
import io
import time
from PIL import Image, ImageDraw
import streamlit as st

from core.handwriting_engine import HandwritingEngine, FONT_MAP, PEN_STYLES
from core.overlay_composer import OverlayComposer, POSTIT_COLORS
from core.gemini_solver import solve_problem_with_gemini
import download_fonts

try:
    from streamlit_paste_button import paste_image_button
except ImportError:
    paste_image_button = None


# 페이지 기본 설정
st.set_page_config(
    page_title="ScribeNote AI | AI 손글씨 해설 솔루션",
    page_icon="✏️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 폰트 다운로드 확인 및 자동 준비
download_fonts.download_fonts()

# 엔진 초기화
@st.cache_resource
def get_composer():
    engine = HandwritingEngine(fonts_dir="fonts")
    composer = OverlayComposer(engine)
    return composer

# 폰트 미리보기 카드 생성 (캐싱)
@st.cache_data
def get_font_preview_image(font_name: str, pen_style: str) -> Image.Image:
    """선택한 손글씨 폰트와 필기구의 실제 필기 예시 카드를 초고속 생성합니다."""
    engine = HandwritingEngine(fonts_dir="fonts")
    w, h = 420, 85
    card = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(card)
    draw.rectangle([0, 0, w - 1, h - 1], outline=(220, 226, 235), width=1)
    
    sample_lines = [
        "f(x) = x² + 2x + 1,  A => B",
        "∴ 정답: x = -1 (풀이 완료!)"
    ]
    res, _ = engine.draw_handwritten_text(
        base_img=card,
        text_lines=sample_lines,
        start_pos=(16, 12),
        font_name=font_name,
        font_size=19,
        pen_style_name=pen_style,
        line_spacing=8,
        apply_jitter=True
    )
    return res.convert("RGB")


from core.auth_manager import (
    register_user, authenticate_user, get_all_users,
    update_user_status, increment_solve_count, change_password,
    get_system_setting, set_system_setting,
    save_user_api_key, get_user_api_key,
    create_session, validate_session, revoke_session
)

try:
    from streamlit_cookies_controller import CookieController
    cookie_controller = CookieController()
except Exception:
    cookie_controller = None


# ----------------- 정식 상용 서비스 테마 CSS 주입 -----------------
CUSTOM_CSS = """
<style>
/* 1. 프리미엄 웹 폰트 (Pretendard) */
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

html, body, [class*="css"], .stMarkdown, .stText, .stButton, input, select, textarea {
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif !important;
    letter-spacing: -0.015em;
}

/* 2. 스트림릿 기본 개발자 요소 은닉 */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}
.stDeployButton {display: none;}

/* 3. 모던 다크 글래스모피즘 배경 */
.stApp {
    background: radial-gradient(circle at 50% 0%, #171b30 0%, #0d111e 50%, #07090f 100%) !important;
    color: #e2e8f0 !important;
}

/* 4. 상용 서비스 카드 스타일 */
.saas-card {
    background: rgba(22, 28, 45, 0.65);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 18px;
    padding: 24px;
    margin-bottom: 24px;
    box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.35);
}

.studio-header {
    font-size: 1.15rem;
    font-weight: 700;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    color: #f1f5f9;
}

.step-badge {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
    color: white;
    font-size: 0.72rem;
    font-weight: 800;
    padding: 4px 10px;
    border-radius: 6px;
    margin-right: 10px;
    letter-spacing: 0.05em;
    display: inline-block;
}

.pro-badge {
    background: rgba(99, 102, 241, 0.2);
    color: #a5b4fc;
    border: 1px solid rgba(99, 102, 241, 0.4);
    font-size: 0.68rem;
    font-weight: 800;
    padding: 3px 8px;
    border-radius: 6px;
    letter-spacing: 0.05em;
    vertical-align: middle;
}

.status-badge-active {
    display: inline-flex;
    align-items: center;
    background: rgba(16, 185, 129, 0.15);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.3);
    font-size: 0.75rem;
    font-weight: 600;
    padding: 4px 12px;
    border-radius: 9999px;
}

/* 5. 메인 액션 버튼 (그라디언트 + 글로우) */
div.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important;
    color: white !important;
    font-weight: 700 !important;
    font-size: 1.05rem !important;
    border-radius: 12px !important;
    border: none !important;
    padding: 0.75rem 1.5rem !important;
    box-shadow: 0 4px 18px rgba(99, 102, 241, 0.4) !important;
    transition: all 0.25s ease !important;
}

div.stButton > button[kind="primary"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 24px rgba(99, 102, 241, 0.6) !important;
}

div.stButton > button[kind="secondary"] {
    background: rgba(30, 41, 59, 0.7) !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    color: #e2e8f0 !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}

div.stButton > button[kind="secondary"]:hover {
    border-color: #6366f1 !important;
    color: #818cf8 !important;
    background: rgba(49, 46, 129, 0.4) !important;
}

/* 6. 사이드바 디자인 */
[data-testid="stSidebar"] {
    background: #0b0f19 !important;
    border-right: 1px solid rgba(255, 255, 255, 0.07);
}

/* 7. 탭 바 모던화 */
div[data-baseweb="tab-list"] {
    background: rgba(15, 23, 42, 0.5);
    border-radius: 10px;
    padding: 4px;
    gap: 6px;
}

div[data-baseweb="tab"] {
    border-radius: 8px;
    padding: 8px 16px;
    color: #94a3b8;
    font-weight: 600;
}

div[data-baseweb="tab"][aria-selected="true"] {
    background: #1e293b;
    color: #ffffff;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

/* 8. 빈 결과 안내 플레이스홀더 */
.empty-placeholder {
    border: 2px dashed rgba(255, 255, 255, 0.15);
    border-radius: 16px;
    padding: 48px 24px;
    text-align: center;
    background: rgba(15, 23, 42, 0.3);
}

/* 9. 상세 풀이 단계별 카드 */
.step-card {
    background: rgba(30, 41, 59, 0.4);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-left: 4px solid #6366f1;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 10px;
    font-size: 0.95rem;
}

.tip-box {
    background: rgba(245, 158, 11, 0.08);
    border: 1px solid rgba(245, 158, 11, 0.25);
    border-radius: 10px;
    padding: 14px 18px;
    margin-top: 14px;
    color: #fde68a;
    font-size: 0.92rem;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ----------------- 자동 로그인 (로그인 상태 유지) 확인 -----------------
if not st.session_state.get("user"):
    # 1. URL 쿼리 파라미터 확인 (지연 없는 0ms 즉시 세션 복원)
    active_token = st.query_params.get("session") or st.query_params.get("auth_token")
    
    # 2. 브라우저 쿠키 확인 (URL 파라미터가 없는 새 탭 / 재방문 시)
    if not active_token and cookie_controller:
        try:
            active_token = cookie_controller.get("scribenote_session")
        except Exception:
            active_token = None
            
    if active_token:
        auto_user = validate_session(active_token)
        if auto_user:
            st.session_state["user"] = auto_user
            st.session_state["session_token"] = active_token
            # URL 파라미터 및 쿠키 동기화 (기한 제한 없는 영구 유지)
            if st.query_params.get("session") != active_token:
                st.query_params["session"] = active_token
            if cookie_controller:
                try:
                    cookie_controller.set("scribenote_session", active_token, max_age=315360000, same_site='lax')
                except Exception:
                    pass
        else:
            # 만료되거나 유효하지 않은 세션 삭제
            if "session" in st.query_params:
                del st.query_params["session"]
            if "auth_token" in st.query_params:
                del st.query_params["auth_token"]
            if cookie_controller:
                try:
                    cookie_controller.remove("scribenote_session")
                except Exception:
                    pass

# ----------------- 로그인 / 회원가입 게이트 -----------------
if not st.session_state.get("user"):
    # 서비스 소개 상단 히어로 배너
    st.markdown("""
    <div style="text-align: center; padding: 40px 10px 20px 10px;">
        <div style="display: inline-flex; align-items: center; gap: 8px; background: rgba(99, 102, 241, 0.15); border: 1px solid rgba(99, 102, 241, 0.3); padding: 6px 14px; border-radius: 9999px; margin-bottom: 16px;">
            <span style="font-size: 0.85rem; color: #a5b4fc; font-weight: 700;">✨ 차세대 교육 솔루션</span>
            <span style="background: #4f46e5; color: white; font-size: 0.65rem; font-weight: 800; padding: 2px 6px; border-radius: 4px;">PRO v3.0</span>
        </div>
        <h1 style="font-size: 2.5rem; font-weight: 800; margin-bottom: 8px; background: linear-gradient(135deg, #ffffff 0%, #cbd5e1 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
            ✏️ ScribeNote AI
        </h1>
        <p style="font-size: 1.05rem; color: #94a3b8; max-width: 600px; margin: 0 auto 30px auto; line-height: 1.6;">
            시험지나 문제집을 캡처하면, 최신 플래그십 AI가 문제를 분석하여 <b>진짜 손으로 푼 듯한 고품질 필기 해설 노트</b>를 즉시 합성해 드립니다.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col_pad1, col_auth, col_pad2 = st.columns([1, 1.4, 1])
    with col_auth:
        st.markdown('<div class="saas-card" style="padding: 28px;">', unsafe_allow_html=True)
        tab_login, tab_signup = st.tabs(["🔑 회원 로그인", "📝 신규 회원가입"])
        
        with tab_login:
            st.markdown("<p style='font-size: 0.9rem; color: #94a3b8; margin-bottom: 16px;'>등록된 계정으로 로그인하여 나만의 손글씨 풀이 노트를 만드세요.</p>", unsafe_allow_html=True)
            login_id = st.text_input("아이디", key="login_id_input", placeholder="아이디를 입력하세요")
            login_pw = st.text_input("비밀번호", type="password", key="login_pw_input", placeholder="비밀번호를 입력하세요")
            
            # 로그인 상태 유지 체크박스 (기본 활성화, 기한 제한 없는 영구 유지)
            remember_me = st.checkbox("🔒 로그인 상태 유지 (영구 자동 로그인)", value=True, key="chk_remember_me", help="체크하시면 브라우저를 닫거나 컴퓨터를 껐다 켜도 직접 [안전 로그아웃]을 누르기 전까지 영구적으로 로그인 상태가 유지됩니다.")
            
            st.write("")
            if st.button("로그인 후 시작하기", type="primary", use_container_width=True, key="btn_do_login"):
                ok, user_info, msg = authenticate_user(login_id, login_pw)
                if ok:
                    st.session_state["user"] = user_info
                    if remember_me:
                        new_token = create_session(user_info["username"])  # 만료 제한 없는 영구 세션
                        st.session_state["session_token"] = new_token
                        st.query_params["session"] = new_token
                        if cookie_controller:
                            try:
                                cookie_controller.set("scribenote_session", new_token, max_age=315360000, same_site='lax')
                            except Exception:
                                pass
                    st.success(f"{user_info['username']}님, 환영합니다!")
                    st.rerun()
                else:
                    st.error(msg)


        with tab_signup:
            st.markdown("<p style='font-size: 0.9rem; color: #94a3b8; margin-bottom: 16px;'>간단한 아이디와 비밀번호만으로 즉시 가입하실 수 있습니다.</p>", unsafe_allow_html=True)
            new_id = st.text_input("희망 아이디 (2자 이상)", key="signup_id_input", placeholder="예: student101")
            new_pw = st.text_input("비밀번호 (4자 이상)", type="password", key="signup_pw_input", placeholder="비밀번호")
            new_pw_conf = st.text_input("비밀번호 확인", type="password", key="signup_pw_conf_input", placeholder="비밀번호 재입력")
            st.write("")
            if st.button("무료 계정 생성하기", use_container_width=True, key="btn_do_signup"):
                if new_pw != new_pw_conf:
                    st.error("비밀번호가 서로 일치하지 않습니다.")
                else:
                    ok, msg = register_user(new_id, new_pw, role="user")
                    if ok:
                        st.success(f"{msg} '로그인' 탭으로 이동하여 로그인해주세요.")
                    else:
                        st.error(msg)
        st.markdown('</div>', unsafe_allow_html=True)
        
    # 하단 3대 특장점 카드
    st.markdown("""
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; max-width: 1050px; margin: 40px auto 20px auto;">
        <div class="saas-card" style="margin-bottom: 0; padding: 20px;">
            <div style="font-size: 1.6rem; margin-bottom: 8px;">⚡</div>
            <div style="font-weight: 700; font-size: 1rem; color: #f8fafc; margin-bottom: 6px;">Gemini 3.x Flash 플래그십</div>
            <div style="font-size: 0.85rem; color: #94a3b8; line-height: 1.5;">최신 멀티모달 추론 엔진이 복잡한 고난도 수식과 논리 기호까지 완벽히 해독하여 정밀 해설을 도출합니다.</div>
        </div>
        <div class="saas-card" style="margin-bottom: 0; padding: 20px;">
            <div style="font-size: 1.6rem; margin-bottom: 8px;">✍️</div>
            <div style="font-weight: 700; font-size: 1rem; color: #f8fafc; margin-bottom: 6px;">실제 학생 손글씨 렌더링</div>
            <div style="font-size: 0.85rem; color: #94a3b8; line-height: 1.5;">6종의 자연스러운 필기체 폰트와 흑색 볼펜, 블루 젤펜, 샤프, 채점용 레드펜 질감을 실감 나게 재현합니다.</div>
        </div>
        <div class="saas-card" style="margin-bottom: 0; padding: 20px;">
            <div style="font-size: 1.6rem; margin-bottom: 8px;">📐</div>
            <div style="font-weight: 700; font-size: 1rem; color: #f8fafc; margin-bottom: 6px;">지능형 맞춤 합성 레이아웃</div>
            <div style="font-size: 0.85rem; color: #94a3b8; line-height: 1.5;">문제 본문을 가리지 않는 여백 직접 필기, 포스트잇 메모지 부착, 우측 모눈노트 확장 등 3가지 모드를 지원합니다.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.stop()


# ----------------- 로그인 사용자 정보 -----------------
current_user = st.session_state.get("user") or {}
if not current_user:
    st.stop()
is_admin = (current_user.get("role") == "admin")
uname = current_user.get("username", "회원")


# ----------------- 상단 글로벌 SaaS 네비게이션 헤더 -----------------
st.markdown(f"""
<div style="display: flex; justify-content: space-between; align-items: center; padding: 14px 24px; background: rgba(22, 28, 45, 0.8); backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 16px; margin-bottom: 24px;">
    <div style="display: flex; align-items: center; gap: 14px;">
        <span style="font-size: 1.8rem;">✏️</span>
        <div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 1.25rem; font-weight: 800; color: #f8fafc; letter-spacing: -0.02em;">ScribeNote AI</span>
                <span class="pro-badge">PRO ENTERPRISE</span>
            </div>
            <div style="font-size: 0.78rem; color: #94a3b8;">수학·과학 문제집 맞춤형 AI 손글씨 해설지 생성 플랫폼</div>
        </div>
    </div>
    <div style="display: flex; align-items: center; gap: 14px;">
        <span class="status-badge-active">● AI 엔진 정상 가동 중 (Gemini 3.x)</span>
        <div style="background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255,255,255,0.1); padding: 5px 14px; border-radius: 10px; font-size: 0.85rem; font-weight: 600; color: #f1f5f9;">
            {'👑' if is_admin else '👤'} {uname} {'(관리자)' if is_admin else '님'}
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


# ----------------- 사이드바 설정 허브 -----------------
with st.sidebar:
    # 1. 회원 프로필 카드
    is_remembered = bool(st.session_state.get("session_token") or st.query_params.get("session"))
    session_badge_html = """
    <div style="margin-top: 8px; font-size: 0.72rem; color: #34d399; background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.25); padding: 4px 8px; border-radius: 6px; text-align: center; font-weight: 500;">
        🔒 로그인 상태 영구 유지 중
    </div>
    """ if is_remembered else ""

    st.markdown(f"""
    <div style="background: rgba(30, 41, 59, 0.5); border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; padding: 16px; margin-bottom: 16px;">
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
            <div style="width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, #4f46e5, #7c3aed); display: flex; align-items: center; justify-content: center; font-size: 1.1rem; color: white;">
                {'👑' if is_admin else '👤'}
            </div>
            <div>
                <div style="font-weight: 700; font-size: 0.95rem; color: #f8fafc;">{uname}</div>
                <div style="font-size: 0.75rem; color: #94a3b8;">{'최고 관리자 계정' if is_admin else '정회원'}</div>
            </div>
        </div>
        <div style="font-size: 0.75rem; color: #cbd5e1; background: rgba(15, 23, 42, 0.6); padding: 6px 10px; border-radius: 6px; text-align: center;">
            누적 풀이 횟수: <b>{current_user.get('solve_count', 0)}회</b>
        </div>
        {session_badge_html}
    </div>
    """, unsafe_allow_html=True)

    if st.button("🚪 안전 로그아웃", key="btn_logout", use_container_width=True):
        current_token = st.session_state.get("session_token") or st.query_params.get("session") or st.query_params.get("auth_token")
        if current_token:
            revoke_session(current_token)
        
        if "session" in st.query_params:
            del st.query_params["session"]
        if "auth_token" in st.query_params:
            del st.query_params["auth_token"]
            
        if cookie_controller:
            try:
                cookie_controller.remove("scribenote_session")
            except Exception:
                pass
                
        st.session_state["user"] = None
        if "session_token" in st.session_state:
            del st.session_state["session_token"]
        st.toast("안전하게 로그아웃되었습니다.", icon="👋")
        st.rerun()

    st.markdown("---")

    # 2. 최고 관리자 전용 대시보드
    if is_admin:
        with st.expander("👑 최고 관리자 전용 패널", expanded=False):
            st.markdown("#### 📊 서비스 운영 현황")
            all_users = get_all_users()
            total_users = len(all_users)
            total_solves = sum(u.get("solve_count", 0) for u in all_users)
            
            c_k1, c_k2 = st.columns(2)
            c_k1.metric("총 회원 수", f"{total_users}명")
            c_k2.metric("총 생성 풀이", f"{total_solves}회")
            
            st.markdown("#### 👥 회원 관리")
            import pandas as pd
            df_users = pd.DataFrame(all_users)
            if not df_users.empty:
                display_df = df_users[["id", "username", "role", "solve_count", "is_active", "created_at"]].copy()
                display_df.columns = ["번호", "아이디", "등급", "풀이", "상태", "가입일"]
                display_df["상태"] = display_df["상태"].map({1: "✅ 정상", 0: "🚫 정지"})
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            manageable_users = [u["username"] for u in all_users if u["username"] != uname]
            if manageable_users:
                target_u = st.selectbox("대상 회원 선택", manageable_users, key="sel_target_u")
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("정상 활성화", key="btn_activate_u", use_container_width=True):
                        update_user_status(target_u, True)
                        st.success(f"{target_u} 활성화 완료")
                        st.rerun()
                with col_b2:
                    if st.button("계정 정지", key="btn_deactivate_u", use_container_width=True):
                        update_user_status(target_u, False)
                        st.warning(f"{target_u} 정지 완료")
                        st.rerun()

            st.markdown("#### 🔑 전 회원 공용 API 키 설정")
            st.caption("관리자가 등록해두면 모든 회원이 개인 키 없이도 고성능 AI 풀이를 이용할 수 있습니다.")
            global_k = get_system_setting("GLOBAL_GEMINI_API_KEY", "")
            new_g_k = st.text_input("공용 API 키", value=global_k, type="password", key="inp_global_key")
            if st.button("공용 API 키 저장", key="btn_save_global_k", use_container_width=True):
                set_system_setting("GLOBAL_GEMINI_API_KEY", new_g_k.strip())
                st.success("공용 API 키가 전역 설정되었습니다!")
                st.rerun()
        st.markdown("---")

    # 3. AI 엔진 및 API 키 설정
    stored_key = ""
    if uname:
        stored_key = get_user_api_key(uname)
    if not stored_key:
        stored_key = get_system_setting("GLOBAL_GEMINI_API_KEY", "")
    if not stored_key:
        try:
            if "GEMINI_API_KEY" in st.secrets:
                stored_key = st.secrets["GEMINI_API_KEY"]
        except Exception:
            pass
    if not stored_key:
        stored_key = os.environ.get("GEMINI_API_KEY", "")

    st.subheader("⚡ AI 엔진 & 인증")
    with st.expander("🔑 Gemini API 키 관리 (계정 자동 저장)", expanded=(not stored_key)):
        new_key = st.text_input(
            "Gemini API Key",
            value=stored_key,
            type="password",
            placeholder="Google AI Studio 발급 무료 키",
            help="Google AI Studio(aistudio.google.com)에서 무료로 즉시 발급 가능합니다.",
            key="inp_user_gemini_key"
        )
        val = new_key.strip() if new_key else ""
        if val and val != stored_key:
            if uname:
                save_user_api_key(uname, val)
            os.environ["GEMINI_API_KEY"] = val
            stored_key = val
            st.success("✅ 계정에 안전하게 저장되었습니다!")
        elif not val and stored_key:
            if uname:
                save_user_api_key(uname, "")
            stored_key = ""

        api_key_input = stored_key
        if not api_key_input:
            st.warning("⚠️ 문제를 풀이하려면 Gemini API 키가 필요합니다.")
            st.caption("👉 [Google AI Studio에서 무료 키 받기](https://aistudio.google.com/apikey)")
        else:
            st.caption("● Gemini API 키가 정상 등록되어 있습니다.")
    
    st.markdown("---")

    # 4. 필기체 및 펜 스타일 스튜디오
    st.subheader("✍️ 필기 스타일 스튜디오")
    selected_pen = st.selectbox(
        "필기구(펜) 스타일",
        options=list(PEN_STYLES.keys()),
        index=0,
        help="0.5mm 흑색 볼펜, 블루 볼펜, 샤프/연필, 채점용 레드펜 등을 지원합니다."
    )

    selected_font = st.selectbox(
        "손글씨 폰트 선택",
        options=list(FONT_MAP.keys()),
        index=0,
        help="원하시는 필기체 스타일을 선택하세요. 아래에 실시간 예시가 표시됩니다."
    )
    
    # 선택된 폰트 실시간 필기체 미리보기 카드
    st.image(
        get_font_preview_image(selected_font, selected_pen),
        caption=f"✍️ [{selected_font.split()[0]}] 실제 필기 예시",
        use_container_width=True
    )

    # 6종 전체 폰트 한눈에 비교하기
    with st.expander("👀 6종 전체 필체 한눈에 비교하기", expanded=False):
        st.caption("현재 선택된 펜 스타일로 6가지 폰트의 실제 글씨체를 비교합니다:")
        for f_name in FONT_MAP.keys():
            st.markdown(f"<div style='font-size:0.83rem; font-weight:600; color:#cbd5e1; margin-top:8px; margin-bottom:3px;'>· {f_name}</div>", unsafe_allow_html=True)
            st.image(get_font_preview_image(f_name, selected_pen), use_container_width=True)

    
    layout_mode = st.radio(
        "합성 레이아웃 모드",
        options=[
            "✍️ 여백 직접 필기 모드 (추천)",
            "📌 포스트잇 메모지 부착 모드",
            "📖 우측 모눈노트 확장 모드"
        ],
        index=0,
        help="문제 본문을 가리지 않고 최적의 풀이 노트를 합성합니다."
    )
    
    postit_color = "노란색"
    if "포스트잇" in layout_mode:
        postit_color = st.selectbox("포스트잇 색상", list(POSTIT_COLORS.keys()), index=0)

    # 5. 모바일 연동 안내
    public_url_file = os.path.join(os.path.dirname(__file__), "assets", "public_url.txt")
    if os.path.exists(public_url_file):
        try:
            with open(public_url_file, "r", encoding="utf-8") as f:
                mob_url = f.read().strip()
            if mob_url:
                with st.expander("📱 스마트폰 접속용 QR 코드", expanded=False):
                    import qrcode
                    qr_img = qrcode.make(mob_url)
                    st.image(qr_img, use_container_width=True)
                    st.markdown(f"[👉 스마트폰 링크 열기]({mob_url})")
        except Exception:
            pass


# ----------------- 메인 작업 스튜디오 (2-Column) -----------------
col_upload, col_preview = st.columns([1, 1], gap="large")

with col_upload:
    st.markdown("""
    <div class="studio-header">
        <span class="step-badge">STEP 1</span>
        <span>문제지 이미지 등록</span>
    </div>
    """, unsafe_allow_html=True)

    # 화면 캡처 클립보드 붙여넣기
    if paste_image_button is not None:
        paste_result = paste_image_button(
            label="📋 화면 캡처 붙여넣기 (Ctrl+V)",
            background_color="#4F46E5",
            hover_background_color="#4338CA",
            errors="ignore",
            key="clipboard_paste_btn"
        )
    else:
        paste_result = None

    uploaded_file = st.file_uploader(
        "또는 문제집/시험지 사진을 직접 업로드하세요",
        type=["jpg", "jpeg", "png"],
        help="선명한 수학, 과학, 논리학 교재 이미지를 권장합니다."
    )
    
    # 이미지 데이터 로드
    if paste_result and paste_result.image_data is not None:
        buf = io.BytesIO()
        paste_result.image_data.convert("RGB").save(buf, format="PNG")
        st.session_state["active_img_bytes"] = buf.getvalue()
        st.session_state["source_type"] = "clipboard"
        st.toast("📋 캡처 이미지를 성공적으로 가져왔습니다!", icon="✅")
    elif uploaded_file is not None:
        st.session_state["active_img_bytes"] = uploaded_file.getvalue()
        st.session_state["source_type"] = "uploaded"

    current_image = None
    image_bytes = st.session_state.get("active_img_bytes", None)
    if image_bytes:
        try:
            current_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception:
            current_image = None

    if current_image:
        st.markdown('<div style="border-radius: 12px; overflow: hidden; border: 1px solid rgba(255,255,255,0.1); margin: 12px 0;">', unsafe_allow_html=True)
        st.image(current_image, caption="등록된 문제집 원본 이미지", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        generate_btn = st.button("🚀 AI 손글씨 해설 노트 생성 시작!", type="primary", use_container_width=True, key="btn_run_solve")
    else:
        st.markdown("""
        <div class="empty-placeholder" style="margin-top: 14px;">
            <div style="font-size: 2.2rem; margin-bottom: 12px;">📷</div>
            <div style="font-weight: 700; color: #f8fafc; font-size: 1rem; margin-bottom: 6px;">등록된 문제가 없습니다</div>
            <div style="font-size: 0.85rem; color: #94a3b8; line-height: 1.5;">
                컴퓨터 화면 캡처(Win + Shift + S) 후 <b>[📋 화면 캡처 붙여넣기]</b>를 누르시거나<br>
                위의 파일 업로더에 문제 사진을 끌어다 놓으세요.
            </div>
        </div>
        """, unsafe_allow_html=True)
        generate_btn = False


with col_preview:
    st.markdown("""
    <div class="studio-header">
        <span class="step-badge">STEP 2</span>
        <span>완성된 손글씨 해설지</span>
    </div>
    """, unsafe_allow_html=True)
    
    composer = get_composer()
    
    if generate_btn and current_image and image_bytes:
        if not api_key_input:
            st.error("❌ Gemini API 키가 설정되지 않았습니다.")
            st.warning("⚠️ 좌측 사이드바의 **[🔑 Gemini AI 엔진 설정]**에서 무료 API 키를 등록해주세요.")
        else:
            with st.spinner("AI가 문제를 정밀 분석하여 손글씨 필기 노트를 렌더링 중입니다..."):
                solution_data = solve_problem_with_gemini(
                    image_bytes=image_bytes,
                    mime_type="image/png",
                    api_key=api_key_input
                )
                time.sleep(0.3)
            
            if solution_data.get("error"):
                st.error(f"❌ AI 문제 풀이 오류: {solution_data.get('error_message')}")
                st.warning("⚠️ 입력하신 Gemini API 키가 활성 상태인지 확인해주세요. (Google AI Studio에서 무료 발급)")
                if "result_img" in st.session_state:
                    del st.session_state["result_img"]
            else:
                if "여백" in layout_mode:
                    result_img = composer.compose_margin_mode(
                        base_img=current_image,
                        solution_data=solution_data,
                        font_name=selected_font,
                        pen_style=selected_pen
                    )
                elif "포스트잇" in layout_mode:
                    result_img = composer.compose_postit_mode(
                        base_img=current_image,
                        solution_data=solution_data,
                        font_name=selected_font,
                        pen_style=selected_pen,
                        postit_color_name=postit_color
                    )
                else: # 모눈노트 확장 모드
                    result_img = composer.compose_notebook_extension_mode(
                        base_img=current_image,
                        solution_data=solution_data,
                        font_name=selected_font,
                        pen_style=selected_pen
                    )
                
                st.session_state["result_img"] = result_img
                st.session_state["solution_data"] = solution_data
                try:
                    increment_solve_count(st.session_state["user"]["username"])
                except Exception:
                    pass
                st.toast("✨ 손글씨 해설지 완성이 완료되었습니다!", icon="🎉")

    if "result_img" in st.session_state:
        # 완성된 이미지 뷰어
        st.markdown('<div style="border-radius: 14px; overflow: hidden; border: 1px solid rgba(255,255,255,0.12); box-shadow: 0 8px 32px rgba(0,0,0,0.3); margin-bottom: 16px;">', unsafe_allow_html=True)
        st.image(st.session_state["result_img"], caption="손글씨 풀이 합성 결과 (고해상도 렌더링)", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        # 이미지 다운로드 버튼
        buf = io.BytesIO()
        st.session_state["result_img"].save(buf, format="PNG")
        byte_im = buf.getvalue()
        
        st.download_button(
            label="💾 완성본 이미지 고화질 다운로드 (PNG)",
            data=byte_im,
            file_name="ScribeNote_손글씨_해설노트.png",
            mime="image/png",
            type="primary",
            use_container_width=True
        )
        
        # 상세 구조화 풀이 리포트 카드
        data = st.session_state.get("solution_data", {})
        used_m = data.get("used_model", "Gemini 3.x Flash")
        
        with st.expander("📝 AI 해설 상세 분석 리포트", expanded=True):
            st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <span style="font-weight: 700; color: #f8fafc; font-size: 1.05rem;">{data.get('problem_title', '문제 해설')}</span>
                <span class="pro-badge">🤖 {used_m}</span>
            </div>
            <div style="font-size: 0.88rem; color: #94a3b8; margin-bottom: 16px;">{data.get('problem_summary', '')}</div>
            """, unsafe_allow_html=True)
            
            st.markdown("**단계별 풀이 과정:**")
            for step in data.get("steps", []):
                st.markdown(f'<div class="step-card">{step}</div>', unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 10px; padding: 12px 16px; margin-top: 14px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 700; color: #34d399;">최종 결론 및 정답</span>
                <span style="font-weight: 800; font-size: 1.1rem; color: #ffffff;">{data.get('final_answer', '')}</span>
            </div>
            """, unsafe_allow_html=True)
            
            if data.get("tip"):
                st.markdown(f"""
                <div class="tip-box">
                    <b>💡 선생님의 핵심 출제 포인트:</b><br>{data.get('tip')}
                </div>
                """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="empty-placeholder">
            <div style="font-size: 2.2rem; margin-bottom: 12px;">✨</div>
            <div style="font-weight: 700; color: #f8fafc; font-size: 1rem; margin-bottom: 6px;">생성 준비 완료</div>
            <div style="font-size: 0.85rem; color: #94a3b8; line-height: 1.5;">
                좌측에서 문제를 지정하신 후 <b>[🚀 AI 손글씨 해설 노트 생성 시작]</b>을 누르시면<br>
                이곳에 자연스러운 필기체 해설지가 실시간 렌더링됩니다.
            </div>
        </div>
        """, unsafe_allow_html=True)

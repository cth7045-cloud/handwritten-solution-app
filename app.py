"""
문제집 손글씨 풀이 합성 웹 애플리케이션 (Handwritten Solution App)
Streamlit 기반 인터랙티브 UI
"""
import os
import io
import time
from PIL import Image
import streamlit as st

from core.handwriting_engine import HandwritingEngine, FONT_MAP, PEN_STYLES
from core.overlay_composer import OverlayComposer, POSTIT_COLORS
from core.gemini_solver import solve_problem_with_gemini, MOCK_SOLUTIONS
import download_fonts
import create_sample_image

try:
    from streamlit_paste_button import paste_image_button
except ImportError:
    paste_image_button = None


# 페이지 기본 설정
st.set_page_config(
    page_title="AI 손글씨 문제집 풀이 노트",
    page_icon="✏️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 폰트 다운로드 확인 및 자동 준비
download_fonts.download_fonts()

# 샘플 이미지 확인 및 자동 준비
sample_img_path = os.path.join(os.path.dirname(__file__), "assets", "sample_math_problem.png")
if not os.path.exists(sample_img_path):
    create_sample_image.generate_sample_problem()

# 엔진 초기화
@st.cache_resource
def get_composer():
    engine = HandwritingEngine(fonts_dir="fonts")
    composer = OverlayComposer(engine)
    return composer

from core.auth_manager import (
    register_user, authenticate_user, get_all_users,
    update_user_status, increment_solve_count, change_password,
    get_system_setting, set_system_setting
)

# ----------------- 로그인 / 회원가입 게이트 -----------------
if not st.session_state.get("user"):
    st.markdown("<h1 style='text-align: center;'>✏️ AI 손글씨 문제집 풀이 노트</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #888;'>회원 전용 서비스입니다. 로그인 후 이용해주세요.</p>", unsafe_allow_html=True)
    st.write("")
    
    col_pad1, col_auth, col_pad2 = st.columns([1, 1.8, 1])
    with col_auth:
        tab_login, tab_signup = st.tabs(["🔑 로그인", "📝 회원가입"])
        
        with tab_login:
            st.subheader("회원 로그인")
            login_id = st.text_input("아이디", key="login_id_input")
            login_pw = st.text_input("비밀번호", type="password", key="login_pw_input")
            
            if st.button("로그인", type="primary", use_container_width=True, key="btn_do_login"):
                ok, user_info, msg = authenticate_user(login_id, login_pw)
                if ok:
                    st.session_state["user"] = user_info
                    st.success(f"{user_info['username']}님, 환영합니다!")
                    st.rerun()
                else:
                    st.error(msg)

        with tab_signup:
            st.subheader("신규 회원가입")
            new_id = st.text_input("희망 아이디 (2자 이상)", key="signup_id_input")
            new_pw = st.text_input("비밀번호 (4자 이상)", type="password", key="signup_pw_input")
            new_pw_conf = st.text_input("비밀번호 확인", type="password", key="signup_pw_conf_input")
            
            if st.button("가입하기", use_container_width=True, key="btn_do_signup"):
                if new_pw != new_pw_conf:
                    st.error("비밀번호가 서로 일치하지 않습니다.")
                else:
                    ok, msg = register_user(new_id, new_pw, role="user")
                    if ok:
                        st.success(f"{msg} '로그인' 탭으로 이동하여 로그인해주세요.")
                    else:
                        st.error(msg)
                        
    st.stop()

# ----------------- 사이드바 설정 -----------------
with st.sidebar:
    current_user = st.session_state.get("user") or {}
    if not current_user:
        st.stop()
    is_admin = (current_user.get("role") == "admin")
    uname = current_user.get("username", "회원")
    
    # 상단 사용자 프로필 및 로그아웃
    col_u, col_lo = st.columns([2.0, 1.2])
    with col_u:
        if is_admin:
            st.markdown(f"👑 **{uname}** `(관리자)`")
        else:
            st.markdown(f"👤 **{uname}** 님")
    with col_lo:
        if st.button("로그아웃", key="btn_logout", use_container_width=True):
            st.session_state["user"] = None
            st.rerun()
            
    st.markdown("---")

    # 최고 관리자 전용 대시보드
    if is_admin:
        with st.expander("👑 최고 관리자 전용 패널", expanded=False):
            st.markdown("#### 👥 회원 목록 및 관리")
            all_users = get_all_users()
            import pandas as pd
            df_users = pd.DataFrame(all_users)
            if not df_users.empty:
                display_df = df_users[["id", "username", "role", "solve_count", "is_active", "created_at"]].copy()
                display_df.columns = ["번호", "아이디", "등급", "풀이횟수", "상태", "가입일"]
                display_df["상태"] = display_df["상태"].map({1: "✅ 정상", 0: "🚫 정지"})
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            st.markdown("#### ⚙️ 회원 상태 변경")
            manageable_users = [u["username"] for u in all_users if u["username"] != uname]
            if manageable_users:
                target_u = st.selectbox("대상 회원", manageable_users, key="sel_target_u")
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("계정 정상 활성화", key="btn_activate_u", use_container_width=True):
                        update_user_status(target_u, True)
                        st.success(f"{target_u} 계정 활성화 완료")
                        st.rerun()
                with col_b2:
                    if st.button("계정 정지", key="btn_deactivate_u", use_container_width=True):
                        update_user_status(target_u, False)
                        st.warning(f"{target_u} 계정 정지 완료")
                        st.rerun()

            st.markdown("#### 🔑 전 회원 공용 API 키 설정")
            st.caption("관리자가 여기에 키를 넣어두면, 일반 회원은 개인 키 없이도 바로 AI 풀이를 쓸 수 있습니다.")
            global_k = get_system_setting("GLOBAL_GEMINI_API_KEY", "")
            new_g_k = st.text_input("공용 API 키", value=global_k, type="password", key="inp_global_key")
            if st.button("공용 API 키 저장", key="btn_save_global_k", use_container_width=True):
                set_system_setting("GLOBAL_GEMINI_API_KEY", new_g_k.strip())
                st.success("공용 API 키가 전역 설정되었습니다!")
                st.rerun()
        st.markdown("---")

    st.title("⚙️ 설정 & 스타일")

    # 모바일/다른 기기 접속 안내
    public_url_file = os.path.join(os.path.dirname(__file__), "assets", "public_url.txt")
    if os.path.exists(public_url_file):
        try:
            with open(public_url_file, "r", encoding="utf-8") as f:
                mob_url = f.read().strip()
            if mob_url:
                with st.expander("📱 스마트폰 접속용 QR 코드", expanded=False):
                    st.caption("스마트폰 카메라로 아래 QR 코드를 비추세요:")
                    import qrcode
                    qr_img = qrcode.make(mob_url)
                    st.image(qr_img, use_container_width=True)
                    st.markdown(f"[👉 스마트폰 링크 열기]({mob_url})")
                st.markdown("---")
        except Exception:
            pass
    
    # 1. 브라우저 localStorage 동기화 컴포넌트 선언
    key_store_path = os.path.join(os.path.dirname(__file__), "components", "key_store")
    saved_browser_key = ""
    if os.path.exists(key_store_path):
        try:
            _key_store_comp = st.components.v1.declare_component("key_store", path=key_store_path)
            saved_browser_key = _key_store_comp(save_key=st.session_state.get("pending_save_key", ""), default="")
        except Exception:
            pass

    # 2. 저장된 키 불러오기 (우선순위: session_state > localStorage > global_setting > secrets > env)
    stored_key = st.session_state.get("gemini_api_key", "")
    if not stored_key and saved_browser_key:
        stored_key = saved_browser_key
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

    local_secrets = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
    if not stored_key and os.path.exists(local_secrets):
        try:
            with open(local_secrets, "r", encoding="utf-8") as f:
                for line in f:
                    if "GEMINI_API_KEY" in line and "=" in line:
                        stored_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception:
            pass

    st.subheader("🔑 Gemini API 설정")
    default_mock = False if stored_key else True
    use_mock = st.checkbox("샘플 모드로 바로 테스트하기 (키 불필요)", value=default_mock)
    
    api_key_input = stored_key
    if not use_mock:
        new_key = st.text_input(
            "Gemini API Key (무료)",
            value=stored_key,
            type="password",
            placeholder="AI Studio에서 발급받은 무료 키 입력",
            help="Google AI Studio(aistudio.google.com)에서 무료로 즉시 발급 가능합니다."
        )
        api_key_input = new_key.strip() if new_key else ""
        
        # 새 키가 입력되었거나 변경된 경우 즉시 영구 저장
        if api_key_input and api_key_input != stored_key:
            st.session_state["gemini_api_key"] = api_key_input
            st.session_state["pending_save_key"] = api_key_input
            os.environ["GEMINI_API_KEY"] = api_key_input
            try:
                os.makedirs(os.path.dirname(local_secrets), exist_ok=True)
                with open(local_secrets, "w", encoding="utf-8") as f:
                    f.write(f'GEMINI_API_KEY = "{api_key_input}"\n')
            except Exception:
                pass
            st.rerun()

        if api_key_input:
            st.success("✅ API 키가 저장되었습니다! (다음 접속 시에도 자동 유지)")
        else:
            st.warning("⚠️ 사진 속 진짜 문제를 풀려면 API 키를 입력해주세요.")
        st.caption("👉 [Google AI Studio에서 무료 키 받기](https://aistudio.google.com/apikey)")
    else:
        st.info("💡 **샘플 모드 활성화됨**: API 키 없이도 손글씨 렌더링과 합성 기능을 바로 확인하실 수 있습니다.")
    
    st.markdown("---")
    st.subheader("✍️ 손글씨 폰트 선택")
    selected_font = st.selectbox(
        "폰트 종류",
        options=list(FONT_MAP.keys()),
        index=0,
        help="다양한 개성의 한글 손글씨 폰트를 선택할 수 있습니다."
    )
    
    st.subheader("🖊️ 필기구(펜) 스타일")
    selected_pen = st.selectbox(
        "펜 종류 및 색상",
        options=list(PEN_STYLES.keys()),
        index=0,
        help="수험생 볼펜, 흑연 연필, 젤펜, 채점용 빨간펜 등을 선택할 수 있습니다."
    )
    
    st.subheader("📐 풀이 합성 모드")
    layout_mode = st.radio(
        "합성 레이아웃",
        options=[
            "✍️ 문제집 빈 공간(여백)에 직접 쓰기 (추천)",
            "📌 포스트잇 메모지 붙이기 (안전 크기)",
            "📖 우측 모눈노트 확장 모드"
        ],
        index=0,
        help="문제 본문을 가리지 않고 비어 있는 연습장/여백에 맞춰 작성합니다."
    )
    
    postit_color = "노란색"
    if "포스트잇" in layout_mode:
        postit_color = st.selectbox("포스트잇 색상", list(POSTIT_COLORS.keys()), index=0)

# ----------------- 메인 영역 -----------------
st.title("✏️ 문제집 손글씨 풀이 노트 생성기")
st.markdown(
    "문제집이나 시험지 사진을 업로드하면, AI가 문제를 풀어 **진짜 손으로 푼 듯한 필기 노트**를 이미지 위에 합성해 드립니다."
)

col_upload, col_preview = st.columns([1, 1], gap="medium")

with col_upload:
    st.subheader("1. 문제집 사진 올리기 / 캡처 붙여넣기")
    
    col_p, col_s = st.columns([1.2, 1], gap="small")
    with col_p:
        if paste_image_button is not None:
            paste_result = paste_image_button(
                label="📋 캡처 붙여넣기 (Ctrl+V)",
                background_color="#1E88E5",
                hover_background_color="#1565C0",
                errors="ignore",
                key="clipboard_paste_btn"
            )
        else:
            paste_result = None
    with col_s:
        use_sample_btn = st.button("📄 샘플 문제 불러오기", use_container_width=True)

    uploaded_file = st.file_uploader(
        "또는 직접 사진을 업로드하세요 (JPG, PNG)",
        type=["jpg", "jpeg", "png"]
    )
    
    # 클립보드 캡처, 업로드, 샘플 순차 처리
    if paste_result and paste_result.image_data is not None:
        buf = io.BytesIO()
        paste_result.image_data.convert("RGB").save(buf, format="PNG")
        st.session_state["active_img_bytes"] = buf.getvalue()
        st.session_state["source_type"] = "clipboard"
        st.toast("📋 클립보드 캡처 이미지를 성공적으로 가져왔습니다!", icon="✅")
    elif uploaded_file is not None:
        st.session_state["active_img_bytes"] = uploaded_file.getvalue()
        st.session_state["source_type"] = "uploaded"
    elif use_sample_btn or ("source_type" in st.session_state and "active_img_bytes" not in st.session_state):
        if os.path.exists(sample_img_path):
            with open(sample_img_path, "rb") as f:
                st.session_state["active_img_bytes"] = f.read()
            st.session_state["source_type"] = "sample"

    current_image = None
    image_bytes = st.session_state.get("active_img_bytes", None)
    if image_bytes:
        try:
            current_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception:
            current_image = None

    if current_image:
        st.image(current_image, caption="선택/캡처된 문제집 이미지", use_container_width=True)
        generate_btn = st.button("🚀 손글씨 풀이 작성 시작!", type="primary", use_container_width=True)
    else:
        st.info("💡 캡처 도구(Win + Shift + S)로 화면을 캡처한 뒤 **[📋 캡처 붙여넣기]** 버튼을 누르시거나, 사진 파일을 업로드해주세요.")
        generate_btn = False

with col_preview:
    st.subheader("2. 손글씨 풀이 결과")
    
    if generate_btn and current_image and image_bytes:
        with st.spinner("AI가 문제를 읽고 손글씨 풀이를 작성 중입니다..."):
            # 1. 문제 풀이 획득
            active_key = None if use_mock else api_key_input
            solution_data = solve_problem_with_gemini(
                image_bytes=image_bytes,
                mime_type="image/png",
                api_key=active_key
            )
            time.sleep(0.3)
            
            if solution_data.get("error"):
                st.error(f"❌ AI 문제 풀이 오류: {solution_data.get('error_message')}")
                st.warning("⚠️ 입력하신 Gemini API 키가 활성 상태인지 확인해주세요. (Google AI Studio에서 무료 발급)")
                if "result_img" in st.session_state:
                    del st.session_state["result_img"]
            else:
                # 2. 합성 레이아웃 적용
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
                else: # 노트 확장 모드
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
                st.success("✨ 손글씨 풀이 완성이 완료되었습니다!")

    if "result_img" in st.session_state:
        st.image(st.session_state["result_img"], caption="손글씨 풀이 합성 결과", use_container_width=True)
        
        # 이미지 다운로드 버튼
        buf = io.BytesIO()
        st.session_state["result_img"].save(buf, format="PNG")
        byte_im = buf.getvalue()
        
        st.download_button(
            label="💾 완성된 풀이 이미지 다운로드 (PNG)",
            data=byte_im,
            file_name="손글씨_문제집_풀이.png",
            mime="image/png",
            use_container_width=True
        )
        
        # 상세 풀이 텍스트 아코디언
        with st.expander("📝 텍스트 풀이 및 사용 모델 상세 보기"):
            data = st.session_state.get("solution_data", {})
            used_m = data.get("used_model")
            if used_m:
                st.success(f"🤖 **풀이에 사용된 AI 모델**: `{used_m}` (최고 성능 순 적용)")
            st.markdown(f"**문제:** {data.get('problem_title', '')}")
            st.markdown(f"**요약:** {data.get('problem_summary', '')}")
            st.markdown("**풀이 단계:**")
            for step in data.get("steps", []):
                st.write(step)
            st.markdown(f"**정답:** `{data.get('final_answer', '')}`")
            if data.get("tip"):
                st.info(data.get("tip"))
    else:
        st.empty()

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

composer = get_composer()

# ----------------- 사이드바 설정 -----------------
with st.sidebar:
    st.title("⚙️ 설정 & 스타일")
    st.markdown("---")

    # 모바일/다른 기기 접속 안내
    public_url_file = os.path.join(os.path.dirname(__file__), "assets", "public_url.txt")
    if os.path.exists(public_url_file):
        try:
            with open(public_url_file, "r", encoding="utf-8") as f:
                mob_url = f.read().strip()
            if mob_url:
                with st.expander("📱 스마트폰 접속용 QR 코드", expanded=True):
                    st.caption("스마트폰 카메라로 아래 QR 코드를 비추세요:")
                    import qrcode
                    qr_img = qrcode.make(mob_url)
                    st.image(qr_img, use_container_width=True)
                    st.markdown(f"[👉 스마트폰 링크 열기]({mob_url})")
                st.markdown("---")
        except Exception:
            pass
    
    st.subheader("🔑 Gemini API 설정")
    use_mock = st.checkbox("샘플 모드로 바로 테스트하기 (키 불필요)", value=True)
    
    api_key_input = ""
    if not use_mock:
        api_key_input = st.text_input(
            "Gemini API Key (무료)",
            type="password",
            placeholder="AI Studio에서 발급받은 무료 키 입력",
            help="Google AI Studio(aistudio.google.com)에서 무료로 즉시 발급 가능합니다."
        )
        st.caption("👉 [Google AI Studio에서 무료 키 받기](https://aistudio.google.com/)")
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
    st.subheader("1. 문제집 사진 올리기")
    
    use_sample_btn = st.button("📄 기본 샘플 문제집 불러오기", use_container_width=True)
    
    uploaded_file = st.file_uploader(
        "또는 직접 사진을 업로드하세요 (JPG, PNG)",
        type=["jpg", "jpeg", "png"]
    )
    
    # 이미지 로드
    current_image = None
    image_bytes = None
    
    if uploaded_file is not None:
        current_image = Image.open(uploaded_file).convert("RGB")
        image_bytes = uploaded_file.getvalue()
        st.session_state["source_type"] = "uploaded"
    elif use_sample_btn or "source_type" in st.session_state:
        if os.path.exists(sample_img_path):
            current_image = Image.open(sample_img_path).convert("RGB")
            with open(sample_img_path, "rb") as f:
                image_bytes = f.read()
            st.session_state["source_type"] = "sample"

    if current_image:
        st.image(current_image, caption="선택된 원본 문제집 이미지", use_container_width=True)
        generate_btn = st.button("🚀 손글씨 풀이 작성 시작!", type="primary", use_container_width=True)
    else:
        st.info("위에서 사진을 업로드하거나 [기본 샘플 문제집 불러오기]를 눌러주세요.")
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
            time.sleep(0.5)
            
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
        with st.expander("📝 텍스트 풀이 상세 보기"):
            data = st.session_state.get("solution_data", {})
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

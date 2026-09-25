"""
Gemini API를 사용하여 문제집 이미지에서 문제를 인식하고 풀이를 생성하는 모듈
google-genai SDK를 사용하며, API 키가 없을 때를 위한 Mock 모드도 지원합니다.
"""
import os
import json
import re
import time
from typing import Dict, Any, List, Optional

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

MODEL_DISPLAY_NAMES = {
    "gemini-3.8-flash": "Gemini 3.8 Flash",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
    "gemini-3.7-flash": "Gemini 3.7 Flash",
    "gemini-3.6-flash": "Gemini 3.6 Flash",
    "gemini-3.5-flash": "Gemini 3.5 Flash",
    "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-2.0-flash": "Gemini 2.0 Flash",
    "gemini-1.5-pro": "Gemini 1.5 Pro",
    "gemini-1.5-flash": "Gemini 1.5 Flash",
}

def format_model_name(raw_name: Optional[str]) -> str:
    """모델 코드명을 공식 명칭(예: Gemini 3.8 Flash)으로 정확하게 변환합니다."""
    if not raw_name:
        return "Gemini 3.8 Flash"
    cleaned = raw_name.replace("models/", "").strip()
    for k in sorted(MODEL_DISPLAY_NAMES, key=len, reverse=True):
        if k in cleaned:
            return MODEL_DISPLAY_NAMES[k]
    return cleaned

# 두 풀이 방식이 함께 쓰는 손글씨 수식 표기 규칙
HANDWRITING_MATH_RULES = """
[★ 손글씨 필기용 수식 작성 절대 규칙 (LaTeX 금지) ★]
- 이것은 사람이 공책/시험지 여백에 펜으로 손글씨를 적는 풀이 노트입니다.
- 절대로 \\frac{1}{3}, \\times, \\theta, \\in, \\mathbb{N}, \\sqrt 등 LaTeX 원시 명령어나 {} $ 기호를 출력하지 마세요!
- 사람이 손으로 쓰는 기호를 그대로 쓰세요: θ, π, α, β, x², θ⁴, a₁, √, ≤, ≥, ≠, ⇒, →, ∫, ∞, ∠, °
- 그리스 문자를 영어로 풀어 쓰지 마세요 (theta, pi 금지 → θ, π). 삼각함수는 "cos θ", "sin 2x" 처럼 띄어 씁니다.
- 분수는 (1/3) 또는 θ²/2, 곱하기는 * 또는 2ab 처럼 생략, 극한은 lim(θ→0+), 소속은 "in 자연수" 처럼 씁니다.
- 한 줄은 공책 한 줄에 들어갈 정도(대략 40자 이내)로 짧게 씁니다.
"""

# 문제 그림 위에 직접 표시하며 푸는 방식 (강사가 시험지 그림에 펜으로 적는 것처럼)
FIGURE_ANNOTATION_RULES = """
[★ 문제 그림 위에 직접 표시하기 (figure_annotations) ★]
실제 강사가 시험지의 그림(도형, 그래프, 좌표 그림)과 선택지 위에 펜으로 표시하며 푸는 것처럼,
이미지 위에 그릴 표시를 "figure_annotations" 배열로 주세요. 시스템이 원본 사진 위에 손글씨로 그려 넣습니다.
- 좌표는 업로드된 이미지 전체 기준 [y, x] 순서이며 0~1000으로 정규화합니다. (왼쪽 위 [0, 0], 오른쪽 아래 [1000, 1000])
- box는 [ymin, xmin, ymax, xmax] (0~1000) 입니다.
- 그림 속 꼭짓점·점의 위치를 정확히 보고 좌표를 정하세요. 글자는 선·글자를 가리지 않는 빈 곳 좌표에 둡니다.
- 그림에 이미 인쇄된 점 이름(A, B, P, O 등)은 다시 쓰지 마세요. label은 길이·값·각도처럼 새로 알아낸 정보만 적습니다.
- 풀이에 실제로 쓰이는 핵심 표시만 4~12개 넣고, 글자는 짧게(8자 이내, note는 20자 이내) 씁니다.
- color는 "blue", "red", "orange", "green" 중 선택하거나 생략(펜 색)합니다.
사용 가능한 type:
  {"type": "label", "point": [y, x], "text": "3a", "color": "blue"}          // 변 옆 빈 곳에 길이·값 적기
  {"type": "highlight", "from": [y, x], "to": [y, x], "color": "orange"}    // 그림 속 기존 선분을 형광펜으로 강조
  {"type": "line", "from": [y, x], "to": [y, x], "dashed": true}            // 보조선 새로 긋기
  {"type": "angle", "vertex": [y, x], "toward1": [y, x], "toward2": [y, x], "text": "θ"}  // 꼭짓점에서 두 방향 사이 각 표시
  {"type": "note", "point": [y, x], "text": "cos α = 4/5", "color": "red"}  // 그림 옆 여백에 짧은 메모
  {"type": "check", "point": [y, x]}                                         // 정답 선택지 번호(예: ④) 위치에 체크
  {"type": "circle", "box": [ymin, xmin, ymax, xmax]}                        // 옳은 보기(ㄱ, ㄷ)나 핵심 값에 동그라미
  {"type": "strike", "box": [ymin, xmin, ymax, xmax]}                        // 틀린 보기(ㄴ)에 빗금
- 객관식이면 정답 선택지에 "check"를, <보기> 문제면 옳은 보기에 "circle", 틀린 보기에 "strike"를 넣으세요.
- circle/strike의 box는 문장 전체가 아니라 보기 기호(ㄱ, ㄴ, ㄷ)나 선택지 번호(①~⑤)만 작게 감싸세요.
- 문제에 그림도 선택지도 없으면 "figure_annotations": [] 로 두세요.
"""

# 정석 풀이와 같은 틀을 쓰되 "작성 원칙"만 다른 풀이 방식들
_EXTRA_PERSONA = """
당신은 친절하고 꼼꼼한 수학/과학 과외 선생님입니다.
업로드된 문제집/교재 사진 속 문제를 파악하고, 학생이 공책에 손글씨로 옮겨 적을 풀이 노트를 작성해야 합니다.
"""

EXTRA_STYLE_PRINCIPLES = {
    "multi_method": _EXTRA_PERSONA + """
[★ 여러 가지 풀이법 비교 작성 원칙 ★]
- 서로 다른 풀이 2~3가지를 보여 주세요. (예: 대수적 계산 / 그래프 이용 / 도형의 성질 / 특수값 대입 / 미분 이용)
- 각 풀이의 첫 줄은 "[풀이 1] 방법 이름" 형식의 소제목이고, 이어서 3~6줄로 핵심만 씁니다.
- 마지막 줄은 "[비교] 어떤 풀이가 언제 더 빠르고 안전한지" 한 줄입니다.
- 정말로 풀이가 한 가지뿐인 단순 문제라면 [풀이 1] 정석 풀이, [풀이 2] 다른 방법으로 검산 으로 씁니다.
- 각 줄의 결론이 같은 정답으로 모여야 합니다.
""",
    "wrong_note": _EXTRA_PERSONA + """
[★ 오답노트형 풀이 작성 원칙 ★]
- 학생이 이 문제에서 실제로 자주 틀리는 지점을 먼저 짚고, 바른 풀이와 재발 방지책을 적는 오답노트입니다.
- steps 는 아래 세 구역으로 씁니다. 각 구역 첫 줄은 소제목입니다.
  "[자주 하는 실수]" 다음 줄부터 1~3줄: 흔한 오개념이나 계산 실수, 그리고 그렇게 하면 나오는 틀린 답
  "[바른 풀이]" 다음 줄부터 4~10줄: ①②③… 번호를 붙인 올바른 풀이
  "[다시 틀리지 않으려면]" 다음 줄부터 1~2줄: 체크포인트
- tip 에는 이 문제의 교훈을 한 줄로 씁니다.
""",
    "hint_steps": _EXTRA_PERSONA + """
[★ 단계별 힌트형 풀이 작성 원칙 ★]
- 학생이 스스로 풀어 보도록 힌트를 먼저 주고, 마지막에 풀이를 보여 줍니다.
- steps 는 "[힌트 1]", "[힌트 2]", "[힌트 3]" 으로 시작하는 줄 2~4개를 먼저 씁니다.
  힌트는 답을 바로 알려 주지 말고 "무엇을 먼저 구해야 할까?" 처럼 방향을 알려 주는 질문·단서로 씁니다.
  힌트 1은 가장 가벼운 단서, 뒤로 갈수록 구체적인 단서입니다.
- 그다음 "[풀이]" 한 줄, 이어서 ①②③… 번호를 붙인 풀이 4~10줄을 씁니다.
""",
    "report": _EXTRA_PERSONA + """
[★ 탐구 레포트형 풀이 작성 원칙 ★]
- A4 보고서에 옮겨 쓸 풀이입니다. 문장은 "~이다", "~한다" 체의 완결된 문장으로 씁니다.
- steps 는 "[문제 분석]" 소제목과 1~3줄(주어진 조건과 구하는 것), 이어서 "[풀이]" 소제목과
  ①②③… 번호를 붙인 6~14줄(각 줄: 무엇을 하는지 한 문장 + 수식)로 씁니다.
- "verification" 에 다른 방법(특수값 대입, 역대입, 단위·범위 확인 등)으로 답을 확인하는 줄 1~3개를 씁니다.
- tip 에는 이 문제로 알 수 있는 결론이나 배운 점을 한 문장(60자 이내)으로 씁니다.
""",
}

STANDARD_PROMPT_TAIL = HANDWRITING_MATH_RULES + FIGURE_ANNOTATION_RULES + """
[★ 그래프/다이어그램 지침 ★]
함수 개형, 부등식의 해, 집합처럼 그림이 이해를 크게 돕는 경우에만 "has_diagram": true와 "diagram"을 작성하세요.
문제에 이미 그림(도형, 좌표 그림)이 있고 그것을 다시 그리는 것뿐이라면 "has_diagram": false로 두세요.
diagram_type 은 "coordinate_plane", "number_line", "venn", "geometry" 중 하나입니다.

반드시 아래 JSON 형식으로만 응답해주세요. 마크다운 ```json ... ``` 태그 없이 순수 JSON 문자열만 출력하세요:
{
    "problem_title": "문제 유형이나 소제목",
    "problem_summary": "인식한 문제 내용 한두 줄 요약",
    "has_diagram": true,
    "diagram": {
        "diagram_type": "coordinate_plane",
        "title": "y = x^2 - 4x + 3",
        "x_range": [-1, 5],
        "y_range": [-2, 6],
        "functions": [{"expr": "x**2 - 4*x + 3", "color": "blue", "label": "y = f(x)"}],
        "points": [{"x": 2, "y": -1, "label": "(2, -1)", "dashed": true}]
    },
    "steps": [
        "[소제목] 위 작성 원칙의 형식을 따른 한 줄",
        "① 설명: 수식"
    ],
    "verification": ["(탐구 레포트형만) 다른 방법으로 답 확인하는 줄"],
    "final_answer": "객관식이면 선택지 번호와 값 함께 (예: ① 1/8, ③ ㄱ, ㄷ), 주관식이면 값 (예: 16)",
    "tip": "한 줄 정리 (40자 이내)",
    "key_concepts": ["이 문제에 쓰인 핵심 개념·공식 이름 1~4개 (각 15자 이내)"],
    "figure_annotations": [
        {"type": "label", "point": [520, 310], "text": "3", "color": "blue"},
        {"type": "check", "point": [905, 640]}
    ]
}
"""

# 기본 우선순위 모델 목록 (실제 존재하는 최신 초고속 비전 플래그십 순서)
BASE_MODEL_PRIORITY = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-pro",
]

# 문제 풀이(이미지 -> 텍스트)에 쓸 수 없는 모델 이름에 들어가는 단어
_NON_SOLVER_MODEL_WORDS = ("tts", "image", "live", "embedding", "transcribe", "computer-use", "customtools", "audio", "robotics", "aqa")


def _model_priority(name: str):
    """최신 flash -> flash-lite -> pro 순, 같은 계열은 버전이 높을수록 먼저. 정식판을 preview보다 먼저."""
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    version = float(m.group(1)) if m else 0.0
    tier = 0 if "flash" in name and "lite" not in name else 1 if "lite" in name else 2
    return (tier, -version, "preview" in name or "exp" in name, name)


# 모델 목록 조회는 요청마다 수백 ms가 걸리므로 프로세스당 한 번만 수행하고 캐시합니다.
_candidate_models_cache: Optional[List[str]] = None


def resolve_candidate_models(client) -> List[str]:
    """
    시도할 모델 순서를 반환합니다.
    GEMINI_MODELS 환경변수(쉼표 구분)가 있으면 그대로 사용하고,
    없으면 API 키에 활성화된 모델 목록을 조회해 gemini-3 계열을 최우선 배치합니다.
    """
    global _candidate_models_cache
    env_models = [m.strip() for m in os.environ.get("GEMINI_MODELS", "").split(",") if m.strip()]
    if env_models:
        return env_models
    if _candidate_models_cache:
        return _candidate_models_cache

    candidate_models = list(BASE_MODEL_PRIORITY)
    try:
        active_from_api = []
        for m in client.models.list():
            m_name = m.name.replace("models/", "") if hasattr(m, "name") and m.name else ""
            if m_name.startswith("gemini") and not any(x in m_name for x in _NON_SOLVER_MODEL_WORDS):
                active_from_api.append(m_name)

        if active_from_api:
            ordered = sorted(active_from_api, key=_model_priority)
            candidate_models = ordered[:4]
            _candidate_models_cache = candidate_models
    except Exception as e:
        print(f"[*] 모델 목록 동적 조회 생략: {e}")
    return candidate_models


def solve_problem_with_gemini(
    image_bytes: bytes,
    mime_type: str = "image/png",
    api_key: Optional[str] = None,
    solve_style: str = "killer_tutor",
    *args,
    **kwargs
) -> Dict[str, Any]:
    """
    Gemini API를 호출하여 이미지 속 문제를 풀이합니다.
    API 키가 없거나 미등록 시 명확한 에러 안내를 반환합니다.
    solve_style: 'killer_tutor' (수능 1타 강사 실전 압축 풀이) | 'standard_concept' (친절한 개념 정석 풀이)
                 | 'multi_method' | 'wrong_note' | 'hint_steps' | 'report' (EXTRA_STYLE_PRINCIPLES)
    """
    if "solve_style" in kwargs:
        solve_style = kwargs["solve_style"]

    secret_key = ""
    try:
        import streamlit as st
        secret_key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        pass
    key = (api_key or os.environ.get("GEMINI_API_KEY", "") or secret_key).strip()
    
    if not key:
        return {
            "error": True,
            "error_message": "Gemini API 키가 설정되지 않았습니다.",
            "problem_title": "Gemini API 키 등록 필요",
            "problem_summary": "문제를 풀이하려면 사이드바에 유효한 Gemini API 키를 등록해야 합니다.",
            "steps": [
                "1. Google AI Studio (https://aistudio.google.com/apikey) 에서 무료 키를 발급받으세요.",
                "2. 좌측 사이드바 [🔑 Gemini AI 엔진 설정]에 API 키를 입력하세요.",
                "3. 키 등록 후 [🚀 AI 손글씨 해설 노트 생성 시작!]을 다시 눌러주세요."
            ],
            "final_answer": "API 키 필요",
            "tip": "발급받으신 API 키는 회원님의 브라우저/계정에 자동 저장됩니다."
        }

    if not genai:
        return {
            "error": True,
            "error_message": "google-genai SDK가 환경에 설치되지 않았습니다.",
            "problem_title": "SDK 미설치",
            "problem_summary": "google-genai 패키지가 필요합니다.",
            "steps": ["pip install google-genai 를 실행하세요."],
            "final_answer": "설치 필요",
            "tip": "서버 환경을 확인해주세요."
        }

    try:
        client = genai.Client(api_key=key)
        
        if solve_style == "killer_tutor":
            prompt = """
당신은 대한민국 최고 수준의 수능/모의평가 수학 1타 강사입니다.
업로드된 문제집/교재 사진 속 문제를 분석하고, 상위권 수험생이나 전문 강사가 시험지 여백에 작성하는 【직관적 그래프 연계와 압축된 핵심 수식 유도】 형태의 최고급 실전 킬러 풀이 노트를 작성해야 합니다.

[★ 수능 1타 강사 실전 압축 풀이 작성 원칙 ★]
1. 장황하고 교과서적인 서술("1단계: 양변을 x에 대하여 미분하여 도함수를 구합니다..." 등)은 빼되,
   수식만 나열하지 말고 각 줄 맨 앞에 "왜 이 줄을 쓰는지"를 2~6글자 한국어 키워드로 붙이세요.
   형식: "키워드: 핵심 수식" 또는 "핵심 수식 ⇒ 키워드". 처음 보는 학생도 줄마다 무엇을 하는지 알 수 있어야 합니다.
2. 전체 6~12줄, 한 줄에는 한 가지 생각만 쓰세요. 결론으로 이어지는 흐름이 보이게 ⇒ 화살표를 활용하세요.
   작성 스타일 예시:
   - "조건 정리: g'(x) = f(x) = ln(x⁴ + 1) - c"
   - "극값 조건: g'(1) = 0 = ln 2 - c ⇒ c = ln 2"
   - "∫₀¹ |f(x)|dx = g(0) ⇒ 높이차"
   - "사각형 넓이: (a₄ - a₁) * g(0) = 2a₄ * g(0)"
   - "근사: θ → 0+ 일 때 1 - cos θ ≈ θ²/2"
   - "대입: mk * eᶜ = 4 * 2 * 2 = 16"
3. 도함수-원함수 연계, 함수 개형, 부호 분석처럼 "그래프를 그려야 비로소 보이는" 경우에만 "has_diagram": true와 "diagram"을 작성하세요.
   문제에 이미 그림(도형, 좌표 그림)이 있고 그것을 다시 그리는 것뿐이라면 "has_diagram": false로 두세요.

지원되는 diagram_type 및 작성 규격:
1. "dual_graph" (★ 수능 킬러/준킬러 도함수-원함수 연계 개형, 위아래 2단 그래프):
{
    "diagram_type": "dual_graph",
    "title": "도함수 f(x)와 원함수 g(x)의 연계 개형",
    "top_graph": {
        "functions": [{"expr": "0.5*x**2 - 0.7", "color": "blue", "label": "f(x)"}],
        "signs": [{"x": -1.5, "text": "+"}, {"x": 0, "text": "-"}, {"x": 1.5, "text": "+"}],
        "points": [{"x": 0, "y": -0.7, "label": "(0, -c)"}]
    },
    "connectors": [-1.18, 0, 1.18], // 상단 영점에서 하단 극값으로 내리는 세로 점선 x좌표들
    "bottom_graph": {
        "functions": [{"expr": "-(x**2 - 1.4)**2 + 1.96", "color": "blue", "label": "g(x)"}],
        "points": [
            {"x": -1.9, "label": "a1", "sub_label": "= a"},
            {"x": -1.0, "label": "a2"},
            {"x": 0.0, "label": "0"},
            {"x": 1.0, "label": "a3"},
            {"x": 1.9, "label": "a4"}
        ],
        "rectangle": {"x1": -1.6, "y1": 0, "x2": 1.6, "y2": 1.5, "color": "green"},
        "hatching": {"x_min": -1.6, "x_max": 1.6, "color": "red"},
        "notes": [{"x": 1.5, "text": "m = 4"}]
    }
}

2. "coordinate_plane" (단일 좌표평면, 함수 그래프, 이차함수, 삼각함수, 정적분 넓이 등):
{
    "diagram_type": "coordinate_plane",
    "title": "y = x^2 - 4x + 3",
    "x_range": [-1, 5],
    "y_range": [-2, 6],
    "functions": [{"expr": "x**2 - 4*x + 3", "color": "blue", "label": "y = f(x)"}],
    "points": [{"x": 2, "y": -1, "label": "(2, -1)", "dashed": true}],
    "shaded_region": {"x_min": 1, "x_max": 3, "y_lower": "0", "y_upper": "x**2 - 4*x + 3"}
}

3. "number_line" (부등식의 해 영역, 수의 범위 등):
{
    "diagram_type": "number_line",
    "title": "부등식의 해 영역",
    "x_range": [-2, 6],
    "intervals": [{"start": 1, "end": 4, "start_closed": false, "end_closed": true, "label": "1 < x <= 4"}]
}

4. "geometry" (삼각형, 사각형, 원 등 기하 문제):
{
    "diagram_type": "geometry",
    "shape": "triangle",
    "title": "직각삼각형 ABC",
    "labels": {"A": "A", "B": "B", "C": "C", "c": "빗변", "angle_B": "90°"}
}

5. "venn" (집합 연산, 포함 관계, 합집합/교집합 등):
{
    "diagram_type": "venn",
    "title": "집합 A, B의 연산",
    "labels": {"A": "A", "B": "B", "intersection": "A∩B"},
    "highlight": "intersection"
}

""" + HANDWRITING_MATH_RULES + FIGURE_ANNOTATION_RULES + """

반드시 아래 JSON 형식으로만 응답해주세요. 마크다운 ```json ... ``` 태그 없이 순수 JSON 문자열만 출력하세요:
{
    "problem_title": "문제 유형이나 소제목",
    "problem_summary": "인식한 문제 내용 한두 줄 요약",
    "has_diagram": true,
    "diagram": {
        "diagram_type": "dual_graph"
    },
    "steps": [
        "키워드: 핵심 수식 1줄",
        "핵심 수식 2줄 ⇒ 키워드"
    ],
    "final_answer": "객관식이면 선택지 번호와 값 함께 (예: ① 1/8, ③ ㄱ, ㄷ), 주관식이면 값 (예: 16)",
    "tip": "실전 킬러 핵심 포인트 한 줄 (40자 이내)",
    "key_concepts": ["이 문제에 쓰인 핵심 개념·공식 이름 1~4개 (각 15자 이내)"],
    "figure_annotations": [
        {"type": "label", "point": [520, 310], "text": "3", "color": "blue"},
        {"type": "check", "point": [905, 640]}
    ]
}
"""
        elif solve_style in EXTRA_STYLE_PRINCIPLES:
            prompt = EXTRA_STYLE_PRINCIPLES[solve_style] + STANDARD_PROMPT_TAIL
        else:
            prompt = """
당신은 친절하고 꼼꼼한 수학/과학/논리학 과외 선생님입니다.
업로드된 문제집/교재 사진 속 문제를 파악하고, 학생이 공책에 적어둔 것처럼 친근하고 명확한 손글씨 풀이 노트를 작성해야 합니다.
[★ 친절한 개념 정석 풀이 작성 원칙 ★]
- 각 단계는 "무엇을 하는지 한국어 한 문장 + 그 단계의 수식" 순서로, 한두 줄 이내로 씁니다.
  예: "① 좌표를 잡는다: O(0, 0), A(1, 0), B(0, 1)", "② 1 - cos θ ≈ θ²/2 를 이용해 근사한다"
- 단계 번호는 ①②③… 을 쓰고, 전체 6~15단계로 기초부터 차근차근 설명합니다.
- 쓰인 개념(공식, 정리)의 이름을 한 번은 밝혀 주세요. 예: "삼각함수의 극한", "근과 계수의 관계"
""" + HANDWRITING_MATH_RULES + FIGURE_ANNOTATION_RULES + """
[★ 그래프/다이어그램 지침 ★]
함수 개형, 부등식의 해, 집합처럼 그림이 이해를 크게 돕는 경우에만 "has_diagram": true와 "diagram"을 작성하세요.
문제에 이미 그림(도형, 좌표 그림)이 있고 그것을 다시 그리는 것뿐이라면 "has_diagram": false로 두세요.
시스템의 손글씨 다이어그램 엔진이 이를 학생이 펜으로 직접 그린 듯한 자연스러운 스케치로 자동 렌더링합니다.

반드시 아래 JSON 형식으로만 응답해주세요. 마크다운 ```json ... ``` 태그 없이 순수 JSON 문자열만 출력하세요:
{
    "problem_title": "문제 유형이나 소제목",
    "problem_summary": "인식한 문제 내용 한두 줄 요약",
    "has_diagram": true,
    "diagram": {
        "diagram_type": "coordinate_plane",
        "title": "y = x^2 - 4x + 3",
        "x_range": [-1, 5],
        "y_range": [-2, 6],
        "functions": [{"expr": "x**2 - 4*x + 3", "color": "blue", "label": "y = f(x)"}],
        "points": [{"x": 2, "y": -1, "label": "(2, -1)", "dashed": true}]
    },
    "steps": [
        "① 첫 번째 단계 설명: 수식",
        "② 두 번째 단계 설명: 수식"
    ],
    "final_answer": "객관식이면 선택지 번호와 값 함께 (예: ① 1/8, ③ ㄱ, ㄷ), 주관식이면 값 (예: 16)",
    "tip": "선생님의 한 줄 꿀팁 또는 자주 하는 실수 포인트 (40자 이내)",
    "key_concepts": ["이 문제에 쓰인 핵심 개념·공식 이름 1~4개 (각 15자 이내)"],
    "figure_annotations": [
        {"type": "label", "point": [520, 310], "text": "3", "color": "blue"},
        {"type": "check", "point": [905, 640]}
    ]
}
"""

        candidate_models = resolve_candidate_models(client)

        response_text = None
        used_model = None
        attempt_logs = []

        part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        json_config = types.GenerateContentConfig(response_mime_type="application/json")

        for model_code in candidate_models:
            config = json_config
            for attempt in range(3):
                t0 = time.monotonic()
                try:
                    resp = client.models.generate_content(model=model_code, contents=[part, prompt], config=config)
                    if resp and resp.text:
                        response_text = resp.text
                        used_model = model_code
                        print(f"[*] {model_code} 응답 {time.monotonic() - t0:.1f}초")
                    else:
                        attempt_logs.append(f"[{model_code}] 빈 응답")
                    break
                except Exception as e:
                    code = getattr(e, "code", None)
                    attempt_logs.append(f"[{model_code}] {e}")
                    print(f"[!] {model_code} 실패({code}) {time.monotonic() - t0:.1f}초: {str(e)[:120]}")
                    if code == 400 and config is not None and attempt == 0:
                        config = None  # JSON 응답 설정을 거부하는 모델이면 설정 없이 한 번 더
                        continue
                    if code in (500, 503) and attempt == 0 and model_code == candidate_models[-1]:
                        time.sleep(1.5)  # 일시적 과부하: 잠깐 쉬고 한 번만 재시도 (429 한도 초과는 재시도해도 소용없어 바로 다음 모델로)
                        continue
                    break  # 그 밖의 오류나 재시도 실패는 다음 모델로
            if response_text:
                break

        if not response_text:
            err_summary = "\n".join(attempt_logs[:4])
            raise Exception(f"사용 가능한 AI 모델을 찾지 못했습니다.\n{err_summary}")
        
        text_output = response_text.strip()
        
        # JSON 블록 안전 추출
        start_idx = text_output.find("{")
        end_idx = text_output.rfind("}")
        if start_idx != -1 and end_idx != -1:
            json_str = text_output[start_idx:end_idx+1]
        else:
            json_str = text_output
            
        result = json.loads(json_str)
        result["used_model"] = format_model_name(used_model)
        return result

    except Exception as e:
        print(f"[!] Gemini API 호출 중 오류 발생: {e}")
        return {
            "error": True,
            "error_message": str(e),
            "problem_title": "AI 풀이 생성 오류",
            "problem_summary": f"오류 원인: {str(e)}",
            "steps": [
                "AI 문제 풀이 호출 중 오류가 발생했습니다.",
                f"세부 오류: {str(e)}",
                "발급받으신 Gemini API 키가 올바른지 확인해주세요."
            ],
            "final_answer": "오류 발생",
            "tip": "구글 AI Studio(aistudio.google.com)에서 발급받은 무료 키를 다시 확인해주세요."
        }

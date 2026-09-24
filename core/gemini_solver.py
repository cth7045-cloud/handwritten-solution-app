"""
Gemini API를 사용하여 문제집 이미지에서 문제를 인식하고 풀이를 생성하는 모듈
google-genai SDK를 사용하며, API 키가 없을 때를 위한 Mock 모드도 지원합니다.
"""
import os
import json
import base64
from typing import Dict, Any, Optional

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
    for k, v in MODEL_DISPLAY_NAMES.items():
        if k in cleaned:
            return v
    return cleaned

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
1. 장황하고 교과서적인 서술("1단계: 양변을 x에 대하여 미분하여 도함수를 구합니다..." 등)을 철저히 배제하세요.
2. 실전 문제 풀이처럼 핵심 관계식과 직관적인 지시 화살표(=> 높이차, => 사각형넓이, => 대칭성 등)를 사용하여 단계별 풀이("steps")를 작성하세요.
   작성 스타일 예시:
   - "g'(x) = f(x) = ln(x^4 + 1) - c"
   - "g'(1) = 0 = ln 2 - c  =>  c = ln 2"
   - "∫_0^1 |f(x)|dx = g(0) => 높이차"
   - "∫_{a1}^{a4} g(x)dx => 사각형넓이 = (a4 - a1) * g(0) = 2a4 * g(0)"
   - "2a4 * ∫_0^1 |f(x)|dx = 2am * ∫_0^1 |f(x)|dx  =>  k = 2, m = 4"
   - "mk * e^c = 4 * 2 * e^(ln 2) = 4 * 2 * 2 = 16"
3. 복잡한 수식이나 미적분, 다항함수, 지수로그, 삼각함수, 도함수와 원함수의 연계 분석이 필요한 경우, 반드시 적극적으로 "has_diagram": true와 함께 "diagram" 객체를 작성해주세요.

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

[★ 손글씨 필기용 수식 작성 절대 규칙 (LaTeX 금지) ★]
- 이것은 사람이 공책/시험지 여백에 펜으로 손글씨를 적는 풀이 노트입니다.
- 절대로 \\frac{1}{3}, \\times, \\in, \\mathbb{N}, \\sqrt 등 LaTeX 원시 명령어를 출력하지 마세요!
- 분수는 (1/3), 곱하기는 *, 소속은 in 자연수, 제곱근은 루트 등으로 사람이 직접 손으로 쓰듯 직관적이고 친근하게 작성하세요.
- 불필요한 LaTeX 중괄호({})나 달러($) 기호도 일체 쓰지 마세요.

반드시 아래 JSON 형식으로만 응답해주세요. 마크다운 ```json ... ``` 태그 없이 순수 JSON 문자열만 출력하세요:
{
    "problem_title": "문제 유형이나 소제목",
    "problem_summary": "인식한 문제 내용 한두 줄 요약",
    "has_diagram": true,
    "diagram": {
        "diagram_type": "dual_graph"
    },
    "steps": [
        "단계별 실전 수식 1줄",
        "단계별 실전 수식 2줄"
    ],
    "final_answer": "최종 정답 단답형 값",
    "tip": "실전 킬러 핵심 포인트 팁"
}
"""
        else:
            prompt = """
당신은 친절하고 꼼꼼한 수학/과학/논리학 과외 선생님입니다.
업로드된 문제집/교재 사진 속 문제를 파악하고, 학생이 공책에 적어둔 것처럼 친근하고 명확한 손글씨 풀이 노트를 작성해야 합니다.
손글씨 필기용이므로 각 단계는 한두 줄 이내로 깔끔하게 정리해주시고, 복잡한 LaTeX 대신 공책에 손글씨로 적기 편한 명확한 기호(예: +, -, *, /, ^2, =>, <=>, v, ^, ~ 등)를 주로 사용해주세요.

[★ 손글씨 필기용 수식 작성 절대 규칙 (LaTeX 금지) ★]
절대로 \\frac, \\times, \\in, \\mathbb, \\sqrt 등 LaTeX 코드를 쓰지 마세요!
사람이 공책에 손으로 적는 것처럼 (1/3), *, in, 자연수 등으로 친근하고 읽기 쉽게 작성하세요.

[★ 시각적 그래프 및 다이어그램 적극 활용 지침 ★]
학생들의 직관적 이해를 돕기 위해, 문제가 함수, 부등식, 기하, 집합, 확률 등 시각화가 가능한 경우 반드시 적극적으로 "has_diagram": true와 함께 "diagram" 객체를 작성해주세요.
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
        "1. 첫 번째 단계 상세 풀이",
        "2. 두 번째 단계 상세 풀이"
    ],
    "final_answer": "최종 정답 또는 결론",
    "tip": "선생님의 한 줄 꿀팁 또는 자주 하는 실수 포인트"
}
"""

        # 기본 우선순위 모델 목록 (실제 존재하는 최신 초고속 비전 플래그십 순서)
        base_priority = [
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-2.5-pro",
            "gemini-1.5-pro",
        ]
        
        # 키에 활성화된 모델 목록 동적 조회 시도
        candidate_models = list(base_priority)
        try:
            active_from_api = []
            for m in client.models.list():
                m_name = m.name.replace("models/", "") if hasattr(m, "name") and m.name else ""
                if "gemini" in m_name and "image" not in m_name and "embedding" not in m_name and "transcribe" not in m_name:
                    active_from_api.append(m_name)
            
            if active_from_api:
                # 3.x 모델이 API 목록에 실제로 존재하면 최우선 배치
                v3_models = [m for m in active_from_api if "gemini-3" in m]
                ordered = v3_models + [m for m in base_priority if m in active_from_api]
                for m in active_from_api:
                    if m not in ordered and not m.startswith("gemini-1."):
                        ordered.append(m)
                if ordered:
                    candidate_models = ordered
        except Exception as e:
            print(f"[*] 모델 목록 동적 조회 생략: {e}")

        response_text = None
        used_model = None
        attempt_logs = []

        part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        for model_code in candidate_models:
            # 1. generate_content with json config
            try:
                config = types.GenerateContentConfig(response_mime_type="application/json")
                resp = client.models.generate_content(
                    model=model_code,
                    contents=[part, prompt],
                    config=config
                )
                if resp and resp.text:
                    response_text = resp.text
                    used_model = model_code
                    break
            except Exception as e1:
                # 2. generate_content without config (thinking 모델 또는 config 거부 시 폴백)
                try:
                    resp = client.models.generate_content(
                        model=model_code,
                        contents=[part, prompt]
                    )
                    if resp and resp.text:
                        response_text = resp.text
                        used_model = model_code
                        break
                except Exception as e2:
                    # 3. Interactions API 폴백
                    try:
                        b64_img = base64.b64encode(image_bytes).decode("utf-8")
                        inter = client.interactions.create(
                            model=model_code,
                            input=[
                                {"type": "text", "text": prompt},
                                {"type": "image", "data": b64_img, "mime_type": mime_type}
                            ]
                        )
                        if inter and hasattr(inter, "output_text") and inter.output_text:
                            response_text = inter.output_text
                            used_model = f"{model_code} (Interactions API)"
                            break
                    except Exception as e3:
                        attempt_logs.append(f"[{model_code}] {e1}")

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

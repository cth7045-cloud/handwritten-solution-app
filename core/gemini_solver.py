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
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Gemini API를 호출하여 이미지 속 문제를 풀이합니다.
    API 키가 없거나 미등록 시 명확한 에러 안내를 반환합니다.
    """
    key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    
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
        
        prompt = """
당신은 친절하고 꼼꼼한 수학/과학/논리학 과외 선생님입니다.
업로드된 문제집/교재 사진 속 문제를 파악하고, 학생이 공책에 적어둔 것처럼 친근하고 명확한 손글씨 풀이 노트를 작성해야 합니다.
손글씨 필기용이므로 각 단계는 한두 줄 이내로 깔끔하게 정리해주시고, 복잡한 LaTeX 대신 공책에 손글씨로 적기 편한 명확한 기호(예: +, -, *, /, ^2, =>, <=>, v, ^, ~ 등)를 주로 사용해주세요.

반드시 아래 JSON 형식으로만 응답해주세요. 마크다운 ```json ... ``` 태그 없이 순수 JSON 문자열만 출력하세요:
{
    "problem_title": "문제 유형이나 소제목 (예: 명제 논리식의 증명)",
    "problem_summary": "인식한 문제 내용 한두 줄 요약",
    "steps": [
        "1. 단계별 풀이 첫 번째 줄",
        "   상세 계산 과정 및 식",
        "2. 두 번째 단계",
        "   상세 계산 과정"
    ],
    "final_answer": "최종 정답 또는 결론",
    "tip": "선생님의 한 줄 꿀팁 또는 자주 하는 실수 포인트"
}
"""
        # 기본 우선순위 모델 목록 (최고 성능 플래그십 순서)
        base_priority = [
            "gemini-3.8-flash",
            "gemini-3.1-pro-preview",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
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
                # base_priority에 있는 것 중 활성화된 것을 우선 순서대로 배치
                ordered = [m for m in base_priority if m in active_from_api]
                # 그 외 활성화된 최신 모델도 뒤에 추가 (구형 2.0 및 1.x 제외)
                for m in active_from_api:
                    if m not in ordered and not m.startswith("gemini-2.0") and not m.startswith("gemini-1."):
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

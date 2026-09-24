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

MOCK_SOLUTIONS = [
    {
        "problem_title": "이차방정식의 근과 계수의 관계",
        "problem_summary": "이차방정식 x² - 4x + 3 = 0의 두 근을 α, β라 할 때, α² + β²의 값을 구하시오.",
        "steps": [
            "1. 근과 계수의 관계 적용:",
            "   두 근의 합 α + β = 4",
            "   두 근의 곱 αβ = 3",
            "2. 곱셈공식 변형 공식 이용:",
            "   α² + β² = (α + β)² - 2αβ",
            "3. 값 대입 및 계산:",
            "   = (4)² - 2 × 3",
            "   = 16 - 6 = 10"
        ],
        "final_answer": "10",
        "tip": "★ Point: (α + β)²을 직접 전개하지 말고 변형 공식 바로 쓰기!"
    },
    {
        "problem_title": "삼각함수의 덧셈정리",
        "problem_summary": "sin(75°)의 정확한 값을 구하시오.",
        "steps": [
            "1. 특수각의 합으로 분해:",
            "   75° = 45° + 30°",
            "2. 덧셈정리 공식 적용:",
            "   sin(45° + 30°) = sin45°cos30° + cos45°sin30°",
            "3. 특수각 삼각비 값 대입:",
            "   = (√2/2) × (√3/2) + (√2/2) × (1/2)",
            "4. 분모 통분 후 정리:",
            "   = (√6 + √2) / 4"
        ],
        "final_answer": "(√6 + √2) / 4",
        "tip": "★ Point: 75° = 45° + 30°, 15° = 45° - 30° 자주 나오는 단골 변형!"
    }
]

def solve_problem_with_gemini(
    image_bytes: bytes,
    mime_type: str = "image/png",
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Gemini API를 호출하여 이미지 속 문제를 풀이합니다.
    API 키가 없거나 실패 시 유용한 안내와 함께 기본 Mock 풀이를 반환할 수 있습니다.
    """
    key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    
    if not key or not genai:
        print("[!] GEMINI_API_KEY가 설정되지 않아 샘플 풀이(Mock) 모드로 동작합니다.")
        return MOCK_SOLUTIONS[0]

    try:
        client = genai.Client(api_key=key)
        
        prompt = """
당신은 친절하고 꼼꼼한 수학/과학/논리학 과외 선생님입니다.
업로드된 문제집/교재 사진 속 문제를 파악하고, 학생이 공책에 적어둔 것처럼 친근하고 명확한 손글씨 풀이 노트를 작성해야 합니다.

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
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2
        )

        # 최고 성능 모델부터 순환 시도 (최상위 지능 3.8-flash -> 최고 추론 2.5-pro -> 고속 추론 2.5-flash -> 2.0-flash)
        candidate_models = [
            "gemini-3.8-flash",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.0-flash"
        ]
        response = None
        used_model = None
        last_err = None

        for model_code in candidate_models:
            try:
                response = client.models.generate_content(
                    model=model_code,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        prompt
                    ],
                    config=config
                )
                if response and response.text:
                    used_model = model_code
                    break
            except Exception as err:
                last_err = err
                print(f"[!] {model_code} 시도 실패: {err}")
                continue

        if not response or not response.text:
            raise Exception(f"AI 모델 응답을 받지 못했습니다. (마지막 시도 에러: {last_err})")
        
        text_output = response.text.strip()
        
        # JSON 블록 안전 추출
        start_idx = text_output.find("{")
        end_idx = text_output.rfind("}")
        if start_idx != -1 and end_idx != -1:
            json_str = text_output[start_idx:end_idx+1]
        else:
            json_str = text_output
            
        result = json.loads(json_str)
        result["used_model"] = used_model
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

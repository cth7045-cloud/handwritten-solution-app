"""
웹 API에서 사용하는 스타일 카탈로그.
API는 한글 표시명 대신 안정적인 영문 id를 주고받고, 여기서 엔진의 키로 변환합니다.
"""
from core.handwriting_engine import FONT_MAP, PEN_STYLES
from core.overlay_composer import POSTIT_COLORS

SOLVE_MODES = {
    "killer_tutor": {
        "label": "수능 1타 강사 실전 압축 풀이",
        "description": "핵심 수식과 => 유도 화살표 위주로 빠르게 전개",
    },
    "standard_concept": {
        "label": "친절한 개념 정석 풀이",
        "description": "개념과 풀이 단계를 기초부터 차근차근",
    },
    "multi_method": {
        "label": "여러 가지 풀이법 비교",
        "description": "대수·그래프·도형 등 2~3가지 풀이를 나란히",
    },
    "wrong_note": {
        "label": "오답노트형 풀이",
        "description": "자주 하는 실수 → 바른 풀이 → 다시 안 틀리는 법",
    },
    "hint_steps": {
        "label": "단계별 힌트형",
        "description": "힌트를 먼저 보고 스스로 풀어 본 뒤 풀이 확인",
    },
    "report": {
        "label": "탐구 레포트형 풀이",
        "description": "문제 분석·개념·풀이·검산·결론을 보고서처럼",
    },
}

# id(폰트 파일명, 확장자 제외) -> 엔진 폰트 키 (FONT_MAP의 한글 표시명)
FONTS = {filename.rsplit(".", 1)[0]: label for label, filename in FONT_MAP.items()}

PENS = {
    "deepblue": "1타 강사 딥블루 잉크 (실전 필기 펜)",
    "blue": "파란색 볼펜",
    "black": "검정색 젤펜",
    "pencil": "연필 / 샤프",
    "red": "빨간색 채점펜",
}

LAYOUTS = {
    "margin": {"label": "여백 직접 필기", "description": "문제집 여백에 직접 풀이 (부족하면 아래로 확장)"},
    "postit": {"label": "포스트잇 부착", "description": "지문을 가리지 않는 메모지 위에 풀이"},
    "notebook": {"label": "모눈노트 확장", "description": "시험지 오른쪽에 격자 노트를 덧대어 풀이"},
    "report": {"label": "A4 레포트", "description": "A4 레포트 용지에 보고서처럼 정리 (PDF 저장)"},
    "cornell": {"label": "코넬노트", "description": "키워드 칸·필기 칸·요약 칸으로 나눈 정리 노트"},
}

POSTITS = {
    "yellow": "노란색",
    "pink": "분홍색",
    "mint": "민트색",
    "sky": "하늘색",
}

assert set(PENS.values()) == set(PEN_STYLES), "PEN_STYLES와 PENS 매핑이 어긋났습니다"
assert set(POSTITS.values()) == set(POSTIT_COLORS), "POSTIT_COLORS와 POSTITS 매핑이 어긋났습니다"


def _rgb_hex(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb[:3])


def catalog_payload() -> dict:
    return {
        "solve_modes": [{"id": k, **v} for k, v in SOLVE_MODES.items()],
        "fonts": [{"id": k, "label": v} for k, v in FONTS.items()],
        "pens": [{"id": k, "label": v, "color": _rgb_hex(PEN_STYLES[v]["color"])} for k, v in PENS.items()],
        "layouts": [{"id": k, **v} for k, v in LAYOUTS.items()],
        "postit_colors": [{"id": k, "label": v, "color": _rgb_hex(POSTIT_COLORS[v])} for k, v in POSTITS.items()],
    }

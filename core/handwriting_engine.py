"""
손글씨 폰트 렌더링 및 필기구(볼펜, 연필, 채점펜 등) 텍스처 효과 엔진
(fontTools 기반 정확한 글리프 검사 및 스마트 수학 기호 폴백 지원)
"""
import os
import random
import math
from typing import List, Tuple, Dict, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from fontTools.ttLib import TTFont

# 사용 가능한 폰트 파일 매핑 (한국어 이름)
FONT_MAP = {
    # 1. 수학 강사/과외 노트 전문 필기체 (실제 수험생·강사 손글씨 스타일)
    "수학 1타 강사 필기체 (암스테르담)": "NanumAmsterdam.ttf",
    "수험생 실전 필기체 (갈맷글)": "NanumGalMaetGeul.ttf",
    "자연스러운 과외노트체 (바른히피)": "NanumBaReunHiPi.ttf",
    "깔끔한 볼펜 풀이체 (중학생)": "NanumJungHakSaeng.ttf",
    "빠른 실전 메모체 (야근하는 김주임)": "NanumKimJuIm.ttf",
    "단정한 손편지체 (손편지체)": "NanumSonPyeonJi.ttf",
    "고려글꼴 (고전 필기체)": "NanumGoryeo.ttf",
    # 2. 클래식 손글씨 폰트
    "나눔손글씨 펜체 (시원한 필기체)": "NanumPenScript-Regular.ttf",
    "단정한 모범생체 (연성체)": "YeonSung-Regular.ttf",
    "깔끔한 필기체 (고운돋움체)": "GowunDodum-Regular.ttf",
    "귀여운 또박또박체 (개구체)": "Gaegu-Regular.ttf",
    "동글동글 캐주얼체 (동글체)": "Dongle-Regular.ttf",
    "감성 손메모체 (하이멜로디체)": "HiMelody-Regular.ttf",
}

# 펜/필기구 색상 프리셋
PEN_STYLES = {
    "1타 강사 딥블루 잉크 (실전 필기 펜)": {
        "color": (16, 45, 142, 245),      # 수능 킬러 풀이 실전 블루잉크
        "jitter_y": 0.85,
        "rotation_deg": 0.8,
        "alpha_var": 16,
    },
    "파란색 볼펜": {
        "color": (28, 65, 175, 235),      # 클래식 수험생 블루
        "jitter_y": 1.0,
        "rotation_deg": 1.0,
        "alpha_var": 20,
    },
    "검정색 젤펜": {
        "color": (25, 25, 25, 245),       # 또렷한 검정
        "jitter_y": 0.6,
        "rotation_deg": 0.6,
        "alpha_var": 12,
    },
    "연필 / 샤프": {
        "color": (60, 60, 60, 210),       # 흑연 회색
        "jitter_y": 1.3,
        "rotation_deg": 1.2,
        "alpha_var": 30,
    },
    "빨간색 채점펜": {
        "color": (215, 35, 35, 235),      # 채점용 레드
        "jitter_y": 1.2,
        "rotation_deg": 1.5,
        "alpha_var": 20,
    }
}

# 폰트에 글리프가 없을 때 사용하는 스마트 대체 딕셔너리
MATH_FALLBACK_MAP = {
    "α": "a",
    "β": "b",
    "γ": "r",
    "θ": "theta",
    "π": "pi",
    "²": "^2",
    "³": "^3",
    "⁴": "^4",
    "ⁿ": "^n",
    "×": " * ",
    "÷": " / ",
    "±": "+/-",
    "≠": "!=",
    "≤": "<=",
    "≥": ">=",
    "∴": "따라서",
    "∵": "왜냐하면",
    "√": "루트",
    "·": "*",
    "→": "->",
    "←": "<-",
    "↔": "<->",
    "⇒": "=>",
    "⇐": "<=",
    "⇔": "<=>",
    "∧": "^",
    "∨": "v",
    "¬": "~",
    "∼": "~",
    "★": "*",
    "☆": "*",
    "📝": "[노트]",
    "📌": "[참고]",
    "▶": ">",
    "▷": ">",
    "■": "*",
    "□": "*",
    "●": "*",
    "○": "*",
    "✔": "V",
    "⭕": "O",
    "❌": "X",
    "∀": "모든",
    "∃": "존재",
    "∈": "in",
    "∉": "not in",
    "⊂": "subset",
    "⊆": "subseteq",
    "∪": "U",
    "∩": "n",
    "∅": "공집합",
    "∞": "inf",
    "∫": "int ",
    "∬": "iint ",
    "∮": "oint ",
    "∑": "sigma ",
    "∏": "pi ",
    "′": "'",
    "″": "''",
}


import re

SYMBOL_FONT_FILE = "DejaVuSans.ttf"
SYMBOL_FONT_SCALE = 0.72

_LATEX_SYMBOLS = {
    "theta": "θ", "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "Delta": "Δ",
    "lambda": "λ", "mu": "μ", "sigma": "σ", "omega": "ω", "phi": "φ", "pi": "π",
    "infty": "∞", "int": "∫", "sum": "Σ", "angle": "∠", "circ": "°", "therefore": "∴",
    "because": "∵", "perp": "⊥", "parallel": "∥", "triangle": "△",
}
_GREEK_WORDS = {"theta": "θ", "alpha": "α", "beta": "β", "pi": "π"}
_SUPERSCRIPT = str.maketrans("0123456789-n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻ⁿ")
_SUBSCRIPT = str.maketrans("0123456789n", "₀₁₂₃₄₅₆₇₈₉ₙ")


def clean_latex_to_handwriting(text: str) -> str:
    """
    AI가 생성한 LaTeX 원시 수식이나 마크다운 기호를
    사람이 공책에 손글씨로 적는 직관적인 자연스러운 수식 표현으로 자동 변환합니다.
    """
    if not text:
        return ""
    
    s = str(text).strip()
    if s.startswith("`") and s.endswith("`"):
        s = s[1:-1].strip()
    
    # 1. 분수 변환: \frac{a}{b}, \dfrac{a}{b} -> (a/b)
    for _ in range(4):
        s = re.sub(r'\\d?frac\{([^{}]+)\}\{([^{}]+)\}', r'(\1/\2)', s)
    
    # 2. 사칙연산 및 특수 연산자
    s = re.sub(r'\\times\b', ' * ', s)
    s = re.sub(r'\\div\b', ' / ', s)
    s = re.sub(r'\\cdot\b', ' * ', s)
    s = re.sub(r'\\pm\b', '+/-', s)
    s = re.sub(r'\\mp\b', '-/+', s)
    
    # 3. 집합 / 범위 기호
    s = re.sub(r'\\in\s*\\mathbb\{N\}', ' in 자연수', s)
    s = re.sub(r'\\in\s*\\mathbb\{R\}', ' in 실수', s)
    s = re.sub(r'\\in\s*\\mathbb\{Z\}', ' in 정수', s)
    s = re.sub(r'\\mathbb\{N\}', '자연수', s)
    s = re.sub(r'\\mathbb\{R\}', '실수', s)
    s = re.sub(r'\\mathbb\{Z\}', '정수', s)
    s = re.sub(r'\\in\b', ' in ', s)
    s = re.sub(r'\\notin\b', ' not in ', s)
    s = re.sub(r'\\subset\b', ' subset ', s)
    
    # 4. 부등호 및 화살표 (사람이 손으로 쓰는 기호 그대로)
    s = re.sub(r'\\le(q)?\b', '≤', s)
    s = re.sub(r'\\ge(q)?\b', '≥', s)
    s = re.sub(r'\\ne(q)?\b', '≠', s)
    s = re.sub(r'\\approx\b', '≒', s)
    s = re.sub(r'\\equiv\b', '≡', s)
    s = re.sub(r'\\Rightarrow\b', '⇒', s)
    s = re.sub(r'\\Leftarrow\b', '⇐', s)
    s = re.sub(r'\\Leftrightarrow\b', '⇔', s)
    s = re.sub(r'\\rightarrow\b', '→', s)
    s = re.sub(r'\\leftarrow\b', '←', s)
    s = re.sub(r'\\to\b', '→', s)

    # 4-1. 그리스 문자 및 기타 기호
    for cmd, sym in _LATEX_SYMBOLS.items():
        s = re.sub(r'\\' + cmd + r'(?![a-zA-Z])', sym, s)
    
    # 5. 첨자: a_{n+1} -> a_(n+1)
    s = re.sub(r'_\{([^{}]+)\}', r'_(\1)', s)
    s = re.sub(r'\^\{([^{}]+)\}', r'^(\1)', s)
    
    # 6. 수학 함수
    s = re.sub(r'\\sqrt\{([^{}]+)\}', r'루트(\1)', s)
    s = re.sub(r'\\sqrt\b', '루트', s)
    s = re.sub(r'\\log\b', 'log', s)
    s = re.sub(r'\\ln\b', 'ln', s)
    s = re.sub(r'\\sin\b', 'sin', s)
    s = re.sub(r'\\cos\b', 'cos', s)
    s = re.sub(r'\\tan\b', 'tan', s)
    s = re.sub(r'\\cdots\b', '...', s)
    s = re.sub(r'\\dots\b', '...', s)
    
    # 7. 텍스트 래퍼 및 불필요 기호
    s = re.sub(r'\\text\{([^{}]+)\}', r'\1', s)
    s = re.sub(r'\\mathrm\{([^{}]+)\}', r'\1', s)
    s = re.sub(r'\\mathbf\{([^{}]+)\}', r'\1', s)
    s = re.sub(r'\\(?:overline|bar|vec|hat)\{([^{}]+)\}', r'\1', s)
    s = s.replace(r'\{', '{').replace(r'\}', '}')
    s = re.sub(r'\\([a-zA-Z]+)', r'\1', s)
    s = s.replace('$', '')

    # 8. AI가 기호 대신 영어로 풀어 쓴 그리스 문자 (costheta, sin theta, theta^2 등)
    s = re.sub(r'(sin|cos|tan)\s*(theta|alpha|beta|pi)(?![a-zA-Z])',
               lambda m: f"{m.group(1)} {_GREEK_WORDS[m.group(2)]}", s)
    for word, sym in _GREEK_WORDS.items():
        s = re.sub(r'(?<![a-zA-Z])' + word + r'(?![a-zA-Z])', sym, s)

    # 9. ASCII 화살표/부등호 -> 손글씨 기호 (<=> 를 먼저 처리)
    s = s.replace('<=>', '⇔').replace('=>', '⇒').replace('->', '→')
    s = s.replace('<=', '≤').replace('>=', '≥').replace('!=', '≠')

    # 10. 간단한 거듭제곱은 위첨자로: x^2 -> x², θ^(4) -> θ⁴, x^-1 -> x⁻¹
    s = s.replace('^°', '°')
    s = re.sub(r'\^(?:\((-?\d{1,2}|n)\)|(-?\d{1,2}|n)(?![0-9A-Za-z]))',
               lambda m: (m.group(1) or m.group(2)).translate(_SUPERSCRIPT), s)

    # 11. 간단한 아래첨자와 극한 표기: a_1 -> a₁, ∫_0 -> ∫₀, lim_(θ→0+) -> lim(θ→0+)
    s = re.sub(r'_(?:\((\d{1,2}|n)\)|(\d{1,2}|n)(?![0-9A-Za-z]))',
               lambda m: (m.group(1) or m.group(2)).translate(_SUBSCRIPT), s)
    s = re.sub(r'lim_\(', 'lim(', s)

    s = re.sub(r'  +', ' ', s)
    return s.strip()


def format_answer(ans) -> str:
    """최종 정답을 손글씨용으로 변환합니다. \\frac{1}{8} -> (1/8) -> 1/8 처럼 불필요한 바깥 괄호는 뺍니다."""
    s = clean_latex_to_handwriting(str(ans or "")).strip()
    # 숫자/분수 하나만 감싼 괄호만 뺍니다 (좌표 (2, 3) 등은 그대로)
    m = re.fullmatch(r'\((-?[0-9A-Za-z.√π]+\s*/\s*[0-9A-Za-z.√π]+|-?[0-9.]+)\)', s)
    return m.group(1).strip() if m else s


class HandwritingEngine:
    def __init__(self, fonts_dir: str = "fonts"):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.fonts_dir = os.path.join(base_dir, fonts_dir)
        self._font_cache = {}
        self._cmap_cache = {}
        self.system_fallback_path = "C:/Windows/Fonts/malgun.ttf" if os.path.exists("C:/Windows/Fonts/malgun.ttf") else None
        # 손글씨 폰트에 없는 수학 기호(θ, π, √, ², ⇒, ≤ ...)만 골라 그릴 보조 폰트
        self.symbol_font_path = os.path.join(self.fonts_dir, "fallback", SYMBOL_FONT_FILE)
        self._symbol_cmap: Optional[set] = None

    # ---------- 보조 기호 폰트 ----------
    def symbol_cmap(self) -> set:
        if self._symbol_cmap is None:
            try:
                tt = TTFont(self.symbol_font_path, lazy=True)
                self._symbol_cmap = set(tt.getBestCmap() or {})
                tt.close()
            except Exception:
                self._symbol_cmap = set()
        return self._symbol_cmap

    def load_symbol_font(self, size: int) -> Optional[ImageFont.FreeTypeFont]:
        # 보조 폰트는 글자가 커 보여서 손글씨 크기에 맞게 줄여 씁니다
        key = ("__symbol__", size)
        if key not in self._font_cache:
            try:
                self._font_cache[key] = ImageFont.truetype(self.symbol_font_path, max(8, round(size * SYMBOL_FONT_SCALE)))
            except Exception:
                self._font_cache[key] = None
        return self._font_cache[key]

    def _uses_symbol_font(self, font_name: str, ch: str) -> bool:
        return (
            not ch.isspace()
            and not self.font_supports_char(font_name, ch)
            and ord(ch) in self.symbol_cmap()
        )

    def text_runs(self, text: str, font_name: str, font_size: int) -> List[Tuple[str, ImageFont.FreeTypeFont]]:
        """텍스트를 '손글씨 폰트로 쓸 부분'과 '보조 기호 폰트로 쓸 부분'으로 나눕니다."""
        main = self.load_font(font_name, font_size)
        symbol = self.load_symbol_font(font_size)
        runs: List[Tuple[str, ImageFont.FreeTypeFont]] = []
        for ch in text:
            f = symbol if symbol is not None and self._uses_symbol_font(font_name, ch) else main
            if runs and runs[-1][1] is f:
                runs[-1] = (runs[-1][0] + ch, f)
            else:
                runs.append((ch, f))
        return runs

    def measure(self, text: str, font_name: str, font_size: int) -> float:
        """여러 폰트가 섞인 텍스트의 가로 길이."""
        return sum(f.getlength(t) for t, f in self.text_runs(text, font_name, font_size))

    def cap_height(self, font_name: str, font_size: int) -> int:
        """한글/대문자 윗선에서 기준선(baseline)까지의 높이."""
        return -self.load_font(font_name, font_size).getbbox("가H", anchor="ls")[1]

    def draw_runs(self, draw: ImageDraw.ImageDraw, baseline_xy: Tuple[float, float], text: str,
                  font_name: str, font_size: int, fill) -> float:
        """기준선에 맞춰 여러 폰트가 섞인 텍스트를 그리고, 그린 가로 길이를 반환합니다."""
        x, y = baseline_xy
        for t, f in self.text_runs(text, font_name, font_size):
            draw.text((x, y), t, font=f, fill=fill, anchor="ls")
            x += f.getlength(t)
        return x - baseline_xy[0]

    def get_font_path(self, font_name: str) -> Optional[str]:
        filename = FONT_MAP.get(font_name, font_name)
        
        # 1. 지정된 폰트 파일 직접 확인
        if os.path.exists(self.fonts_dir):
            filepath = os.path.join(self.fonts_dir, filename)
            if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
                return filepath
            
            # 2. 대소문자 무시 매칭
            for f in os.listdir(self.fonts_dir):
                if f.lower() == filename.lower():
                    cand = os.path.join(self.fonts_dir, f)
                    if os.path.getsize(cand) > 1000:
                        return cand
            
            # 3. fonts_dir에 있는 아무 한글 TTF 폰트나 폴백
            for f in os.listdir(self.fonts_dir):
                if f.endswith(".ttf"):
                    cand = os.path.join(self.fonts_dir, f)
                    if os.path.getsize(cand) > 50000:
                        return cand
                        
        # 4. 리눅스 / 윈도우 시스템 한글 폰트 폴백
        system_candidates = [
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "C:/Windows/Fonts/malgun.ttf",
            "C:/Windows/Fonts/NanumGothic.ttf"
        ]
        for sc in system_candidates:
            if os.path.exists(sc):
                return sc
                
        return None

    def get_font_cmap(self, font_name: str) -> set:
        """TTFont를 사용해 폰트의 실제 글리프 지원 목록(유니코드 코드포인트 세트)을 캐싱합니다."""
        if font_name in self._cmap_cache:
            return self._cmap_cache[font_name]
        
        path = self.get_font_path(font_name)
        if not path or not os.path.exists(path):
            self._cmap_cache[font_name] = set()
            return self._cmap_cache[font_name]

        try:
            tt = TTFont(path, fontNumber=0)
            cmap = tt.getBestCmap()
            supported_codes = set(cmap.keys()) if cmap else set()
            tt.close()
            self._cmap_cache[font_name] = supported_codes
            return supported_codes
        except Exception:
            self._cmap_cache[font_name] = set()
            return self._cmap_cache[font_name]

    def load_font(self, font_name: str, size: int) -> ImageFont.FreeTypeFont:
        cache_key = (font_name, size)
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]
        
        path = self.get_font_path(font_name)
        if path:
            try:
                font = ImageFont.truetype(path, size)
                self._font_cache[cache_key] = font
                return font
            except Exception as e:
                print(f"[!] 폰트 로드 실패 ({path}): {e}")
        
        # fonts 디렉토리 내의 아무 TTF라도 시도
        if os.path.exists(self.fonts_dir):
            for f in os.listdir(self.fonts_dir):
                if f.endswith(".ttf"):
                    cand = os.path.join(self.fonts_dir, f)
                    try:
                        font = ImageFont.truetype(cand, size)
                        self._font_cache[cache_key] = font
                        return font
                    except Exception:
                        pass
        
        # load_default()는 캐시하지 않음
        return ImageFont.load_default()

    def font_supports_char(self, font_name: str, char: str) -> bool:
        """폰트가 해당 문자를 진짜로 지원하는지 확인합니다. 한글 음절은 항상 True로 보존합니다."""
        cp = ord(char)
        # 한글 음절(가-힣) 및 한글 자모는 절대 미지원 처리하지 않음
        if 0xAC00 <= cp <= 0xD7A3 or 0x3131 <= cp <= 0x318E:
            return True
        cmap = self.get_font_cmap(font_name)
        if not cmap:
            return True
        return cp in cmap

    def sanitize_math_text(self, text: str, font_name: str) -> str:
        """
        손글씨 폰트와 보조 기호 폰트 모두에 없는 글자만 자연스러운 대체 문자로 바꿔
        글자 깨짐(□)을 막습니다. θ, √, ² 처럼 보조 폰트에 있는 기호는 그대로 둡니다.
        """
        cleaned = []
        for ch in text:
            if ch.isspace() or self.font_supports_char(font_name, ch) or ord(ch) in self.symbol_cmap():
                cleaned.append(ch)
            else:
                cleaned.append(MATH_FALLBACK_MAP.get(ch, ""))
        return "".join(cleaned)

    def wrap_text(self, text: str, font_name: str, font_size: int, max_width: int) -> List[str]:
        """지정된 최대 너비에 맞게 텍스트를 줄바꿈합니다 (단어가 길거나 수식인 경우 글자 단위 분할로 절대 잘리지 않음)."""
        sanitized = self.sanitize_math_text(clean_latex_to_handwriting(text), font_name)

        def width(t: str) -> float:
            return self.measure(t, font_name, font_size)

        lines = []
        for raw_line in sanitized.split("\n"):
            if not raw_line.strip():
                lines.append("")
                continue

            curr_line = ""
            for word in raw_line.split(" "):
                test_line = f"{curr_line} {word}".strip() if curr_line else word
                if width(test_line) <= max_width:
                    curr_line = test_line
                    continue
                if curr_line:
                    lines.append(curr_line)
                    curr_line = ""
                if width(word) <= max_width:
                    curr_line = word
                    continue
                # 단어/수식 자체가 max_width보다 긴 경우 글자 단위로 안전하게 분할
                sub_line = ""
                for ch in word:
                    if width(sub_line + ch) <= max_width:
                        sub_line += ch
                    else:
                        if sub_line:
                            lines.append(sub_line)
                        sub_line = ch
                curr_line = sub_line
            if curr_line:
                lines.append(curr_line)
        return lines


    def draw_handwritten_text(
        self,
        base_img: Image.Image,
        text_lines: List[str],
        start_pos: Tuple[int, int],
        font_name: str,
        font_size: int,
        pen_style_name: str = "파란색 볼펜",
        line_spacing: int = 12,
        apply_jitter: bool = True
    ) -> Tuple[Image.Image, Tuple[int, int]]:
        """
        사람이 직접 쓴 듯한 자연스러운 텍스트(약간의 흔들림, 회전, 투명도 변화)를 그립니다.
        """
        font = self.load_font(font_name, font_size)
        style = PEN_STYLES.get(pen_style_name, list(PEN_STYLES.values())[0])
        base_color = style["color"]
        jitter_y = style["jitter_y"] if apply_jitter else 0
        rot_range = style["rotation_deg"] if apply_jitter else 0
        alpha_var = style["alpha_var"] if apply_jitter else 0

        overlay = Image.new("RGBA", base_img.size, (255, 255, 255, 0))

        # 모든 단어를 같은 기준선(baseline)에 맞춰 씁니다.
        # (단어마다 자기 글자 윗선에 맞추면 '-', '=' 처럼 키 작은 기호가 위로 붕 떠 보입니다)
        cap = self.cap_height(font_name, font_size)
        symbol_font = self.load_symbol_font(font_size)
        metric_fonts = [font] + ([symbol_font] if symbol_font is not None else [])
        ascent = max(f.getmetrics()[0] for f in metric_fonts)
        descent = max(f.getmetrics()[1] for f in metric_fonts)
        pad = 10

        curr_x, curr_y = start_pos
        max_x = curr_x

        for line in text_lines:
            line_cleaned = clean_latex_to_handwriting(line)
            line_sanitized = self.sanitize_math_text(line_cleaned, font_name)
            if not line_sanitized.strip():
                curr_y += font_size + line_spacing
                continue

            baseline_y = curr_y + cap
            line_x = curr_x
            words = line_sanitized.split(" ")
            for i, word in enumerate(words):
                if not word:
                    line_x += int(font_size * 0.3)
                    continue

                word_to_draw = word + (" " if i < len(words) - 1 else "")
                word_w = self.measure(word_to_draw, font_name, font_size)

                dy = random.uniform(-jitter_y, jitter_y)
                angle = random.uniform(-rot_range, rot_range)
                a_offset = random.randint(-alpha_var, alpha_var)
                actual_alpha = max(110, min(255, base_color[3] + a_offset))
                actual_color = (base_color[0], base_color[1], base_color[2], actual_alpha)

                patch_w = max(1, int(word_w) + pad * 2)
                patch_h = ascent + descent + pad * 2
                patch = Image.new("RGBA", (patch_w, patch_h), (255, 255, 255, 0))
                self.draw_runs(ImageDraw.Draw(patch), (pad, pad + ascent), word_to_draw, font_name, font_size, actual_color)

                if abs(angle) > 0.1:
                    rotated_patch = patch.rotate(angle, resample=Image.BICUBIC, expand=True)
                else:
                    rotated_patch = patch

                # 회전으로 커진 만큼 보정해 글자 중심 위치를 유지
                draw_x = int(line_x - pad - (rotated_patch.width - patch_w) / 2)
                draw_y = int(baseline_y - ascent - pad + dy - (rotated_patch.height - patch_h) / 2)
                overlay.alpha_composite(rotated_patch, (max(0, draw_x), max(0, draw_y)))

                line_x += word_w
                max_x = max(max_x, line_x)

            curr_y += font_size + line_spacing

        if base_img.mode != "RGBA":
            result_img = base_img.convert("RGBA")
        else:
            result_img = base_img.copy()

        result_img.alpha_composite(overlay)
        return result_img, (max_x, curr_y)

    def draw_grading_circle(
        self,
        base_img: Image.Image,
        center: Tuple[int, int],
        radius: int = 40,
        color: Tuple[int, int, int, int] = (220, 30, 30, 220),
        width: int = 4
    ) -> Image.Image:
        """
        선생님이 손으로 채점할 때 그리는 자연스러운 붉은색 타원형 동그라미(⭕)를 그립니다.
        """
        overlay = Image.new("RGBA", base_img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)

        cx, cy = center
        rx = radius * random.uniform(0.9, 1.15)
        ry = radius * random.uniform(0.8, 0.95)
        
        points = []
        steps = 45
        for s in range(steps + 1):
            theta = math.radians(s * (380 / steps) - 20)
            r_var = random.uniform(-1.2, 1.2)
            x = cx + (rx + r_var) * math.cos(theta)
            y = cy + (ry + r_var) * math.sin(theta)
            points.append((x, y))

        for i in range(len(points) - 1):
            draw.line([points[i], points[i + 1]], fill=color, width=width)

        result = base_img.convert("RGBA") if base_img.mode != "RGBA" else base_img.copy()
        result.alpha_composite(overlay)
        return result

    def draw_answer_circle(
        self,
        base_img: Image.Image,
        bbox: Tuple[float, float, float, float],
        color: Tuple[int, int, int, int] = (16, 45, 142, 235),
        width: int = 2,
        left_room: Optional[float] = None
    ) -> Image.Image:
        """
        수학 해설지에서 최종 정답 주위에 사람이 손으로 펜을 돌려 그린 듯한 자연스러운 타원 동그라미를 그립니다.
        left_room: 정답 왼쪽에 있는 여백(px). 주면 동그라미가 그보다 왼쪽으로 나가지 않도록
        중심을 오른쪽으로 옮겨 "정답:" 글자를 덮지 않게 합니다.
        """
        overlay = Image.new("RGBA", base_img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)

        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        pad_x = 5
        pad_y = 6
        rx = max(12.0, (x2 - x1) / 2 + pad_x) * random.uniform(0.98, 1.08)
        ry = max(14.0, (y2 - y1) / 2 + pad_y) * random.uniform(0.95, 1.05)
        if left_room is not None:
            # 흔들림(±0.8)과 선 굵기까지 고려한 동그라미의 가장 왼쪽 끝이 여백 안에 들어오게
            reach = rx + 0.8 + width / 2
            cx = max(cx, x1 - left_room + reach)

        points = []
        steps = 45
        start_angle = random.uniform(-35, -15)
        total_angle = random.uniform(375, 395)
        for s in range(steps + 1):
            theta = math.radians(start_angle + s * (total_angle / steps))
            jitter = random.uniform(-0.8, 0.8)
            x = cx + (rx + jitter) * math.cos(theta)
            y = cy + (ry + jitter) * math.sin(theta)
            points.append((x, y))

        for i in range(len(points) - 1):
            draw.line([points[i], points[i + 1]], fill=color, width=width)

        result = base_img.convert("RGBA") if base_img.mode != "RGBA" else base_img.copy()
        result.alpha_composite(overlay)
        return result


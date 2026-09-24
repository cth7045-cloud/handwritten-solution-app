"""
실제 모의고사/수능 스타일의 일반적인 수학 문제집 샘플 이미지 생성기
(인위적인 풀이공간 구분선, 박스, 가이드 텍스트 완전 제거)
"""
import os
from PIL import Image, ImageDraw, ImageFont

def generate_sample_problem():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(base_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    out_path = os.path.join(assets_dir, "sample_math_problem.png")

    # 가로 1000, 세로 720 (일반 시험지 비율, 단정하고 깔끔한 미색 종이 질감)
    img = Image.new("RGB", (1000, 720), (254, 254, 253))
    draw = ImageDraw.Draw(img)

    # 폰트 로드 (맑은 고딕 볼드 및 기본)
    try:
        font_header_title = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 21)
        font_header_sub = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 18)
        font_prob_num = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 25)
        font_body = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 21)
        font_small = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 16)
    except Exception:
        font_header_title = font_header_sub = font_prob_num = font_body = font_small = ImageFont.load_default()

    # 1. 일반 모의고사 상단 헤더
    draw.text((45, 18), "2026학년도 대학수학능력시험 6월 모의평가 문제지", fill=(30, 30, 30), font=font_header_title)
    draw.text((750, 20), "제 2 교시   수학 영역", fill=(20, 20, 20), font=font_header_sub)
    
    # 헤더 이중 구분선 (실제 시험지 스타일)
    draw.line([(45, 52), (955, 52)], fill=(40, 40, 40), width=2)
    draw.line([(45, 56), (955, 56)], fill=(120, 120, 120), width=1)

    # 2. 문제 번호 및 본문 지문 (인위적인 박스 전혀 없이 실제 시험지 그대로)
    draw.text((50, 85), "07.", fill=(15, 15, 15), font=font_prob_num)

    prob_line1 = "이차방정식 x² - 4x + 3 = 0 의 두 실근을 각각 α, β라고 할 때,"
    prob_line2 = "α² + β² 의 값은?  [3점]"

    draw.text((95, 87), prob_line1, fill=(25, 25, 25), font=font_body)
    draw.text((95, 122), prob_line2, fill=(25, 25, 25), font=font_body)

    # 3. 객관식 보기 선지 (실제 시험지처럼 5개 선지 가로 정렬)
    choices = [
        "①  6",
        "②  8",
        "③  10",
        "④  12",
        "⑤  14"
    ]
    start_x = 95
    step_x = 175
    choice_y = 185
    for i, choice in enumerate(choices):
        draw.text((start_x + i * step_x, choice_y), choice, fill=(30, 30, 30), font=font_body)

    # 하단 페이지 번호 (실제 시험지 느낌)
    draw.line([(45, 680), (955, 680)], fill=(210, 210, 210), width=1)
    draw.text((490, 690), "1", fill=(140, 140, 140), font=font_small)

    img.save(out_path, "PNG")
    print(f"[OK] General exam-style sample problem created: {out_path}")

if __name__ == "__main__":
    generate_sample_problem()

"""
다양한 오픈소스 한글 손글씨 폰트를 다운로드하는 스크립트
Google Fonts 및 오픈소스 저장소에서 직접 TTF 파일을 받아 fonts/ 디렉토리에 저장합니다.
"""
import os
import urllib.request

FONTS = {
    # 1. 수학 강사/과외 노트 전문 필기체 (실제 수험생·강사 손글씨 스타일)
    "NanumAmsterdam.ttf": "https://ssl.pstatic.net/static/clova/service/clova_ai/event/handwriting/download/%EB%82%98%EB%88%94%EC%86%90%EA%B8%80%EC%94%A8%20%EC%95%94%EC%8A%A4%ED%85%8C%EB%A5%B4%EB%8B%B4.ttf",
    "NanumBaReunHiPi.ttf": "https://ssl.pstatic.net/static/clova/service/clova_ai/event/handwriting/download_211102/NanumBaReunHiPi.ttf",
    "NanumGalMaetGeul.ttf": "https://ssl.pstatic.net/static/clova/service/clova_ai/event/handwriting/download/%EB%82%98%EB%88%94%EC%86%90%EA%B8%80%EC%94%A8%20%EA%B0%88%EB%A7%B7%EA%B8%80.ttf",
    "NanumJungHakSaeng.ttf": "https://ssl.pstatic.net/static/clova/service/clova_ai/event/handwriting/download/%EB%82%98%EB%88%94%EC%86%90%EA%B8%80%EC%94%A8%20%EC%A4%91%ED%95%99%EC%83%9D.ttf",
    "NanumKimJuIm.ttf": "https://ssl.pstatic.net/static/clova/service/clova_ai/event/handwriting/download/%EB%82%98%EB%88%94%EC%86%90%EA%B8%80%EC%94%A8%20%EC%95%BC%EA%B7%BC%ED%95%98%EB%8A%94%20%EA%B9%80%EC%A3%BC%EC%9E%84.ttf",
    "NanumSonPyeonJi.ttf": "https://ssl.pstatic.net/static/clova/service/clova_ai/event/handwriting/download/%EB%82%98%EB%88%94%EC%86%90%EA%B8%80%EC%94%A8%20%EC%86%90%ED%8E%B8%EC%A7%80%EC%B2%B4.ttf",
    "NanumGoryeo.ttf": "https://ssl.pstatic.net/static/clova/service/clova_ai/event/handwriting/download/%EB%82%98%EB%88%94%EC%86%90%EA%B8%80%EC%94%A8%20%EA%B3%A0%EB%A0%A4%EA%B8%80%EA%BF%84.ttf",
    # 2. 클래식 Google Fonts 손글씨
    "NanumPenScript-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/nanumpenscript/NanumPenScript-Regular.ttf",
    "Gaegu-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/gaegu/Gaegu-Regular.ttf",
    "YeonSung-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/yeonsung/YeonSung-Regular.ttf",
    "Dongle-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/dongle/Dongle-Regular.ttf",
    "HiMelody-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/himelody/HiMelody-Regular.ttf",
    "GowunDodum-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/gowundodum/GowunDodum-Regular.ttf",
}

def download_fonts(target_dir="fonts"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_target_dir = os.path.join(base_dir, target_dir)
    os.makedirs(full_target_dir, exist_ok=True)
    
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for filename, url in FONTS.items():
        filepath = os.path.join(full_target_dir, filename)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            continue
            
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req) as response, open(filepath, "wb") as out_file:
                out_file.write(response.read())
            print(f"[OK] Downloaded: {filename} ({os.path.getsize(filepath):,} bytes)")
        except Exception as e:
            print(f"[FAIL] {filename} download failed: {e}")

if __name__ == "__main__":
    download_fonts()

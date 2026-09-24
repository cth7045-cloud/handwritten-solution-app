"""
다양한 오픈소스 한글 손글씨 폰트를 다운로드하는 스크립트
Google Fonts 및 오픈소스 저장소에서 직접 TTF 파일을 받아 fonts/ 디렉토리에 저장합니다.
"""
import os
import urllib.request

FONTS = {
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

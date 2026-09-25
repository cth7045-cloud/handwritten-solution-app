# ✏️ 문제집 손글씨 풀이 노트 생성기 (Handwritten Solution App)

문제집이나 시험지 사진을 업로드하면, AI가 문제를 인식하고 단계별 풀이를 생성한 뒤 **실제 손으로 푼 듯한 손글씨 필기 노트**를 사진 위에 합성해 주는 프로그램입니다.

---

## 🌟 주요 특징

1. **다양한 한글 손글씨 폰트 지원**:
   - 나눔손글씨 펜 (시원시원한 만년필/볼펜 필기체)
   - 개구체 (귀엽고 또박또박한 손글씨)
   - 연성체 (단정하고 깔끔한 모범생 필기체)
   - 동글체 (동글동글 캐주얼 손글씨)
   - 하이멜로디 (감성적인 손메모 느낌)
   - 고운돋움 (정돈된 필기체)
2. **리얼한 필기구 스타일**:
   - **파란 볼펜 (Blue Ballpoint)**: 실제 수험생들이 가장 많이 쓰는 클래식 블루 잉크
   - **연필 / 샤프 (Pencil Graphite)**: 부드러운 흑연 질감과 자연스러운 농담
   - **검정 젤펜 (Black Gel Pen)**: 또렷하고 짙은 검정 펜
   - **빨간 채점펜 (Red Grading Pen)**: 선생님 채점 느낌의 빨간색 잉크
3. **손글씨 자연스러움 알고리즘**:
   - 기계적인 일직선 출력을 탈피하여 단어별 미세 높낮이(Jitter)와 회전각, 필압(Alpha) 변화 적용
   - 정답 부분에 손으로 그린 듯한 **빨간 채점 동그라미(⭕)** 효과 자동 합성
   - 한글 손글씨 폰트에서 누락되기 쉬운 그리스 문자/수학 기호 자동 감지 및 스마트 치환 (글자 깨짐 방지)
4. **3가지 스마트 합성 레이아웃**:
   - 📌 **포스트잇 메모지 모드 (추천)**: 빽빽한 문제집 위에도 본문을 가리지 않고 실제 메모지를 붙인 듯 그림자와 함께 합성 (노랑, 핑크, 민트, 스카이블루)
   - ✍️ **원본 사진 여백 직접 필기 모드**: 문제집의 빈 여백에 자연스럽게 끄적여 푼 느낌
   - 📖 **모눈노트 확장 모드**: 문제집 우측에 격자 연습장을 붙여 넉넉한 풀이 공간 확보
5. **Gemini API 연동**:
   - Google AI Studio의 무료 API 키로 동작

---

## 🏗️ 서비스 구조 (웹 버전)

```
[브라우저 / 스마트폰 / 태블릿]  web/  (HTML + JS, 설치형 PWA)
   │  사진 촬영·파일·Ctrl+V 붙여넣기 → 브라우저에서 1800px로 축소
   │
   ├─ POST /api/solve   이미지 → 풀이 JSON        (Gemini 호출, 수 초)
   └─ POST /api/render  이미지 + 풀이 JSON + 스타일 → PNG  (AI 없이 ~0.1초)
                         │
             [FastAPI 서버]  server/   ← Docker 컨테이너 1개 (Cloud Run 등)
                         │
             core/  손글씨·그래프·레이아웃 합성 엔진 (Pillow)
```

- **AI 풀이와 렌더링을 분리**했기 때문에, 풀이가 한 번 나오면 펜·글씨체·레이아웃을 바꿀 때 AI를 다시 부르지 않고 즉시 다시 그립니다.
- 같은 `seed`면 같은 필체 흔들림이 재현되고, **[다시 쓰기]** 를 누르면 새로운 흔들림으로 다시 씁니다.
- AI가 만든 그래프 함수식은 `core/safe_math.py`의 안전한 수식 해석기로만 계산합니다(`eval` 미사용).

## 🚀 실행 방법

### 웹 서비스 (권장)
```bash
pip install -r server/requirements.txt
export GEMINI_API_KEY=발급받은_키          # Windows: set GEMINI_API_KEY=...
uvicorn server.main:app --reload --port 8000
```
브라우저에서 `http://localhost:8000` 접속. API 문서는 `http://localhost:8000/api/docs`.

| 환경변수 | 설명 |
|---|---|
| `GEMINI_API_KEY` | (필수) 서버가 사용할 Gemini API 키. 사용자에게는 노출되지 않습니다. |
| `GEMINI_MODELS` | (선택) 시도할 모델을 쉼표로 고정. 예: `gemini-2.5-flash`. 비우면 키에 열린 모델을 한 번 조회해 최신 순으로 사용합니다. |
| `WEB_CONCURRENCY` | (선택) Docker 실행 시 워커 수, 기본 2 |

### 24시간 배포 (Google Cloud Run 예시)
```bash
gcloud run deploy handwritten-note --source . --region asia-northeast3 \
  --allow-unauthenticated --min-instances 1 --memory 1Gi \
  --set-env-vars GEMINI_MODELS=gemini-2.5-flash --set-secrets GEMINI_API_KEY=gemini-key:latest
```
`--min-instances 1` 로 항상 1대를 켜 두면 첫 요청 지연(콜드 스타트)이 없습니다. 같은 `Dockerfile`로 Fly.io, Render, Railway에도 그대로 배포할 수 있습니다.

### 테스트
```bash
pip install pytest httpx
python -m pytest
```

### (구버전) Streamlit 앱
```bash
streamlit run app.py
```

---

## 🔑 Gemini 무료 API 키 발급 방법
1. [Google AI Studio](https://aistudio.google.com/)에 접속하여 구글 계정으로 로그인합니다.
2. 좌측 상단 또는 화면 중앙의 **"Get API key"** 버튼을 누릅니다.
3. **"Create API key"**를 클릭하여 생성된 키를 복사합니다. (신용카드 등록 불필요, 100% 무료)
4. 웹 앱 사이드바의 `Gemini API Key` 입력칸에 붙여넣고 사용하시면 됩니다.

---

## 📂 프로젝트 구조

```
handwritten-solution-app/
├── server/                 # 웹 API 서버 (FastAPI)
│   ├── main.py             # /api/solve, /api/render, /api/styles, 정적 파일 제공
│   ├── rendering.py        # 업로드 이미지 전처리 + 합성 렌더링
│   ├── catalog.py          # 폰트/펜/레이아웃 id ↔ 엔진 키 매핑
│   └── requirements.txt
├── web/                    # 프론트엔드 (index.html, app.js, styles.css, PWA manifest)
├── core/
│   ├── gemini_solver.py    # Gemini 문제 인식 및 풀이 JSON 생성
│   ├── handwriting_engine.py  # 손글씨 렌더링 (흔들림·회전·필압), LaTeX → 손글씨 수식 변환
│   ├── diagram_engine.py   # 손그림 그래프 (좌표평면, 도함수-원함수 2단 연계 등)
│   ├── overlay_composer.py # 여백 / 포스트잇 / 모눈노트 합성
│   └── safe_math.py        # AI 함수식 안전 계산기
├── fonts/                  # 오픈소스 한글 손글씨 폰트 (.ttf)
├── tests/                  # pytest
├── Dockerfile              # 웹 서비스 컨테이너
└── app.py                  # (구버전) Streamlit UI
```

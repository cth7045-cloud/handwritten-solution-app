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
                  │                    │
   core/ 손글씨·그래프·레이아웃 엔진      PostgreSQL (Neon 등)
         (Pillow)                       회원 · 로그인 세션 · 일일 사용량 · 풀이 기록
```

- **AI 풀이와 렌더링을 분리**했기 때문에, 풀이가 한 번 나오면 펜·글씨체·레이아웃을 바꿀 때 AI를 다시 부르지 않고 즉시 다시 그립니다.
- 같은 `seed`면 같은 필체 흔들림이 재현되고, **[다시 쓰기]** 를 누르면 새로운 흔들림으로 다시 씁니다.
- AI가 만든 그래프 함수식은 `core/safe_math.py`의 안전한 수식 해석기로만 계산합니다(`eval` 미사용).
- **회원제**: 로그인해야 풀이할 수 있고, 회원별 하루 풀이 한도(기본 20회, 관리자는 무제한)가 있습니다. AI 호출이 실패하면 한도에서 차감하지 않습니다.
- **내 기록**: 풀이가 저장되어 나중에 다시 열고 펜·글씨체를 바꿔 다시 그릴 수 있습니다 (회원별 최근 100개).
- **관리자 화면**: 회원 목록·오늘 사용량, 이용 정지/해제, 회원별 한도 변경, 비밀번호 초기화.
- **보안**: 비밀번호 PBKDF2(60만 회) 해시, HttpOnly·SameSite 세션 쿠키(DB에는 토큰 해시만 저장), 로그인 연속 실패 제한, 다른 사이트에서 보낸 요청 차단, CSP 보안 헤더.

## 🚀 실행 방법

### 웹 서비스 (로컬)
```bash
pip install -r server/requirements.txt
export GEMINI_API_KEY=발급받은_키
export ADMIN_PASSWORD=관리자_비밀번호       # 관리자 아이디는 기본 "갈빙"
uvicorn server.main:app --reload --port 8000
```
브라우저에서 `http://localhost:8000` 접속. API 문서는 `http://localhost:8000/api/docs`.
`DATABASE_URL`을 비우면 `data/app.db`(SQLite)를 씁니다. `.env.example`을 `.env`로 복사해 값을 채우고 `uvicorn server.main:app --reload --env-file .env`로 실행해도 됩니다.

| 환경변수 | 설명 |
|---|---|
| `GEMINI_API_KEY` | (필수) 서버가 사용할 Gemini API 키. 사용자에게는 노출되지 않습니다. |
| `ADMIN_PASSWORD` | (필수) 관리자 비밀번호. 서버가 시작할 때마다 이 값으로 관리자 계정을 맞춥니다. 바꾸면 관리자 기존 로그인은 모두 끊깁니다. |
| `ADMIN_USERNAME` | 관리자 아이디, 기본 `갈빙` |
| `DATABASE_URL` | 배포 시 필수. PostgreSQL 주소 (예: `postgresql://user:pw@host/db?sslmode=require`) |
| `DAILY_SOLVE_LIMIT` | 회원 기본 하루 풀이 한도, 기본 20 (관리자 화면에서 회원별로 변경 가능) |
| `ALLOW_SIGNUP` | `false`면 신규 가입을 막습니다 (기본 `true`) |
| `HISTORY_LIMIT` | 회원별 보관할 풀이 기록 수, 기본 100 |
| `SESSION_DAYS` | 로그인 유지 기간(일), 기본 365 |
| `GEMINI_MODELS` | 시도할 모델을 쉼표로 고정. 예: `gemini-2.5-flash`. 비우면 키에 열린 모델을 한 번 조회해 최신 순으로 사용 |
| `WEB_CONCURRENCY` | Docker 실행 시 워커 수, 기본 2 |

> 비밀번호·API 키·DB 주소는 **절대 저장소에 커밋하지 마세요.** 이 저장소는 공개(public)입니다. 배포 환경의 Secret으로만 넣습니다.

### 현재 운영 중인 배포 (Render + Supabase)
- 주소: https://handwritten-note.onrender.com
- 서버: Render 무료 플랜, 싱가포르 (`WEB_CONCURRENCY=1`, 무료 플랜 메모리 512MB에 맞춤). 15분간 접속이 없으면 잠들고, 다음 접속 때 깨어나는 데 약 1분 걸립니다.
- DB: Supabase(싱가포르) PostgreSQL. 앱 전용 계정 `hwapp`이 공개 API에 노출되지 않는 `app` 스키마만 사용합니다. 세션 풀러(IPv4) 주소로 접속합니다.
- **`claude/ai-handwriting-solution-generator-5kyxsz` 브랜치에 push하면 자동으로 다시 배포됩니다.**
- 환경변수(`GEMINI_API_KEY`, `ADMIN_PASSWORD`, `DATABASE_URL` 등)는 Render 대시보드 → 서비스 → Environment에서 관리합니다.

### 24시간 배포 (Google Cloud Run + Neon PostgreSQL)

Cloud Run 컨테이너는 재시작하면 내부 파일이 사라지므로, 회원·기록은 외부 PostgreSQL에 저장해야 합니다.

#### 가장 쉬운 방법: Cloud Shell에서 스크립트 한 번 실행
1. [Google Cloud 콘솔](https://console.cloud.google.com)에서 프로젝트를 만들고 결제 계정을 연결합니다 (Cloud Run 사용에 필요).
2. [neon.tech](https://neon.tech)에서 무료 PostgreSQL을 만들고 연결 주소(`postgresql://...`)를 복사합니다.
3. [Cloud Shell](https://shell.cloud.google.com)을 열고 아래를 붙여넣습니다. 중간에 Gemini API 키, 관리자 비밀번호, DB 주소를 물어봅니다(입력값은 화면에 안 보이고 Secret Manager에만 저장).
```bash
git clone -b claude/ai-handwriting-solution-generator-5kyxsz https://github.com/cth7045-cloud/handwritten-solution-app
cd handwritten-solution-app
bash deploy/cloudrun.sh
```
끝나면 접속 주소가 출력됩니다. 코드를 업데이트한 뒤에는 `git pull && bash deploy/cloudrun.sh`만 다시 실행하면 됩니다(저장된 비밀값은 그대로 사용).
항상 켜두려면 `MIN_INSTANCES=1 bash deploy/cloudrun.sh` (첫 접속 지연 없음, 대신 상시 과금).

#### 직접 명령어로 배포하기

**1) 데이터베이스 만들기 (Neon, 무료 플랜 가능)**
[neon.tech](https://neon.tech) 가입 → 프로젝트 생성(아시아 리전 선택) → 연결 문자열(`postgresql://...`)을 복사합니다.
(Supabase, Cloud SQL 등 다른 PostgreSQL도 됩니다. 단 Supabase 무료 플랜은 7일간 사용이 없으면 일시 중지됩니다.)

**2) Google Cloud 준비** ([gcloud CLI 설치](https://cloud.google.com/sdk/docs/install) 후)
```bash
gcloud auth login
gcloud config set project <프로젝트ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com artifactregistry.googleapis.com

# 비밀값을 Secret Manager에 저장
# (셸 기록에 남기기 싫으면 printf 없이 `gcloud secrets create 이름 --data-file=-` 실행 후 값을 붙여넣고 Ctrl+D)
printf '%s' '<Gemini API 키>'      | gcloud secrets create gemini-key     --data-file=-
printf '%s' '<관리자 비밀번호>'     | gcloud secrets create admin-password --data-file=-
printf '%s' '<Neon 연결 문자열>'    | gcloud secrets create database-url   --data-file=-

# Cloud Run 기본 서비스 계정이 Secret을 읽을 수 있게 권한 부여
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')
gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

**3) 배포** (저장소 루트에서)
```bash
gcloud run deploy handwritten-note --source . --region asia-northeast3 \
  --allow-unauthenticated --min-instances 1 --memory 1Gi --cpu 1 --timeout 120 \
  --set-env-vars GEMINI_MODELS=gemini-2.5-flash,DAILY_SOLVE_LIMIT=20 \
  --set-secrets GEMINI_API_KEY=gemini-key:latest,ADMIN_PASSWORD=admin-password:latest,DATABASE_URL=database-url:latest
```
배포가 끝나면 `https://handwritten-note-xxxx.asia-northeast3.run.app` 주소가 나옵니다. 폰·태블릿·PC 어디서나 접속하고, 브라우저 메뉴의 "홈 화면에 추가"로 앱처럼 쓸 수 있습니다.

- `--min-instances 1`: 항상 1대를 켜 두어 첫 접속 지연(콜드 스타트)이 없습니다. 대신 켜져 있는 시간만큼 소액 과금되므로 [가격 계산기](https://cloud.google.com/products/calculator)로 확인하세요. 비용을 아끼려면 `0`으로 두면 됩니다(처음 접속만 몇 초 느려짐).
- 관리자 비밀번호 변경: `printf '%s' '<새 비밀번호>' | gcloud secrets versions add admin-password --data-file=-` 후 같은 배포 명령을 다시 실행.
- 코드 업데이트: 같은 `gcloud run deploy` 명령을 다시 실행하면 무중단으로 교체됩니다.

### 테스트
```bash
pip install -r server/requirements.txt pytest httpx
python -m pytest                                   # SQLite
TEST_DATABASE_URL=postgresql://... python -m pytest  # 실제 PostgreSQL로 검증
```
GitHub에 push하면 `.github/workflows/test.yml`이 SQLite와 PostgreSQL 두 환경에서 자동으로 테스트합니다.

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
│   ├── api_auth.py         # 회원가입/로그인/관리자 API
│   ├── accounts.py         # 회원·세션·사용량·풀이 기록 저장소
│   ├── db.py / config.py   # DB 스키마, 환경변수 설정
│   ├── security.py         # 세션 쿠키, 로그인 시도 제한, 보안 헤더
│   ├── rendering.py        # 업로드 이미지 전처리 + 합성 렌더링
│   ├── catalog.py          # 폰트/펜/레이아웃 id ↔ 엔진 키 매핑
│   └── requirements.txt
├── web/                    # 프론트엔드 (로그인, 만들기, 내 기록, 관리자 화면 / PWA)
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

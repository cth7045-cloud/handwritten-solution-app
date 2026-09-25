#!/usr/bin/env bash
# Google Cloud Run 원클릭 배포 스크립트
# Google Cloud Shell(https://shell.cloud.google.com)에서 저장소 폴더로 이동한 뒤 실행하세요:
#   bash deploy/cloudrun.sh
# 비밀값(API 키, 관리자 비밀번호, DB 주소)은 화면에 표시되지 않게 입력받아 Secret Manager에만 저장합니다.
set -euo pipefail

SERVICE="${SERVICE:-handwritten-note}"
REGION="${REGION:-asia-northeast3}"            # 서울
MIN_INSTANCES="${MIN_INSTANCES:-0}"            # 1이면 항상 켜둠(첫 접속 지연 없음, 대신 상시 과금)
DAILY_SOLVE_LIMIT="${DAILY_SOLVE_LIMIT:-20}"
GEMINI_MODELS="${GEMINI_MODELS:-gemini-3.8-flash,gemini-3.5-flash-lite,gemini-2.5-flash}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

say() { printf '\n\033[1;34m▶ %s\033[0m\n' "$*"; }

PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
if [ -z "$PROJECT" ] || [ "$PROJECT" = "(unset)" ]; then
  read -rp "Google Cloud 프로젝트 ID를 입력하세요: " PROJECT
  gcloud config set project "$PROJECT" >/dev/null
fi
say "프로젝트: $PROJECT / 지역: $REGION / 서비스 이름: $SERVICE"

say "필요한 Google Cloud 기능 켜는 중 (처음엔 1~2분 걸립니다)"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com

put_secret() {
  local name="$1" prompt="$2" val answer
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    read -rp "'$name' 값이 이미 저장돼 있습니다. 새 값으로 바꿀까요? (y/N) " answer
    [ "$answer" = "y" ] || [ "$answer" = "Y" ] || return 0
  fi
  read -rsp "$prompt (입력해도 화면에 안 보입니다): " val
  echo
  if [ -z "$val" ]; then
    echo "값이 비어 있어 중단합니다." >&2
    exit 1
  fi
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    printf '%s' "$val" | gcloud secrets versions add "$name" --data-file=- >/dev/null
  else
    printf '%s' "$val" | gcloud secrets create "$name" --data-file=- --replication-policy=automatic >/dev/null
  fi
  echo "  '$name' 저장 완료"
}

say "비밀값 저장"
put_secret gemini-key "Gemini API 키"
put_secret admin-password "관리자(아이디: 갈빙) 비밀번호"
put_secret database-url "PostgreSQL 연결 주소 (Neon에서 복사한 postgresql://...)"

say "Cloud Run이 비밀값을 읽고 소스를 빌드할 수 있도록 권한 설정"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for s in gemini-key admin-password database-url; do
  gcloud secrets add-iam-policy-binding "$s" \
    --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor" >/dev/null
done
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:$SA" --role="roles/run.builder" --condition=None >/dev/null \
  || echo "  (참고) run.builder 권한 부여를 건너뛰었습니다. 빌드 권한 오류가 나면 이 메시지를 알려주세요."

say "빌드 및 배포 중 (처음엔 5~10분 걸립니다)"
gcloud run deploy "$SERVICE" --source "$ROOT" --region "$REGION" \
  --allow-unauthenticated --min-instances "$MIN_INSTANCES" --max-instances 3 \
  --memory 1Gi --cpu 1 --timeout 120 \
  --set-env-vars "^|^GEMINI_MODELS=${GEMINI_MODELS}|DAILY_SOLVE_LIMIT=${DAILY_SOLVE_LIMIT}" \
  --set-secrets "GEMINI_API_KEY=gemini-key:latest,ADMIN_PASSWORD=admin-password:latest,DATABASE_URL=database-url:latest" \
  --quiet

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
say "배포 완료! 접속 주소: $URL"
echo "관리자 아이디 '갈빙'과 방금 입력한 비밀번호로 로그인하세요."

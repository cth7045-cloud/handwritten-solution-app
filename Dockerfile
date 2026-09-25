# 웹 서비스(FastAPI) 컨테이너 - Google Cloud Run / Fly.io / Render 등 어디서나 동작
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app

COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY core core
COPY server server
COPY web web
COPY fonts fonts

EXPOSE 8080
# --proxy-headers: Cloud Run 등 HTTPS 프록시 뒤에서 https로 인식 (로그인 쿠키 Secure 설정)
CMD ["sh", "-c", "uvicorn server.main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*'"]

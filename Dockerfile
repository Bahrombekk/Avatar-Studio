# Avatar Studio — ilova qatlami (frontend build + FastAPI server).
#
# DIQQAT: bu image YENGIL ilova qatlamini (API, /studio panel, RAG, suhbat saqlash,
# config/auth/metrics) o'z ichiga oladi. To'liq GPU lip-sync inference (MuseTalk/torch)
# ALOHIDA og'ir bog'liqliklarni (models/MuseTalk/requirements.txt) + NVIDIA runtime +
# models/ hajmini talab qiladi — buni `musetalk` conda muhitida (run.sh) yoki maxsus
# CUDA image'da bajaring. Bu image API/panelni va torch'siz ishlaydigan qismlarni beradi.

# ── 1-bosqich: frontend build (Vite) ──
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── 2-bosqich: backend runtime ──
FROM python:3.10-slim
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1 LOG_FORMAT=json AVATAR_STUDIO_SKIP_WARMUP=1

# ffmpeg — TTS/video birlashtirish uchun (yengil qism ham foydalanadi).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
# Vite build natijasini frontend/dist ga joylaymiz (main.py shu yerdan /studio beradi).
COPY --from=frontend /app/frontend/dist /app/frontend/dist

EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]

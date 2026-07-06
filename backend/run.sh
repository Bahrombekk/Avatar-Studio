#!/usr/bin/env bash
# ============================================================
#  Avatar Studio backend — FastAPI (paket: app.main:app), port 8100.
#  Portativ: barcha yo'llar shu skript joylashuviga nisbatan hisoblanadi.
#  Avval o'rnatilgan bo'lishi kerak:  bash setup.sh  (loyiha ildizida)
#  Ishga tushirish:  bash backend/run.sh
# ============================================================
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # backend/
ROOT="$(cd "$BASE/.." && pwd)"                          # loyiha ildizi
ENV_DIR="${AVATAR_ENV_DIR:-$ROOT/envs/avatar}"          # bundle qilingan conda muhiti
PYTHON="$ENV_DIR/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "XATO: Python muhiti topilmadi: $PYTHON"
    echo "      Avval loyiha ildizida o'rnating:  bash setup.sh"
    exit 1
fi

# ── Modellar (loyiha ichida) ──
export MT_DIR="${MT_DIR:-$ROOT/models/MuseTalk}"
export LP_DIR="${LP_DIR:-$ROOT/models/LivePortrait}"
export PYTHONPATH="$MT_DIR:${PYTHONPATH:-}"

# ── Real-time: JUMLA-DARAJALI OQIM (call-ai uslubi) ──
# GPT jumla yozishi bilanoq o'sha jumlani TTS qiladi va videoga uzatadi — TTS
# GPT bilan PARALLEL ketadi, birinchi ovoz/video ~1-2s da chiqadi (butun javob
# TTS tugashini kutmaydi). O'chirish: RT_SENTENCE_STREAM=0.
export RT_SENTENCE_STREAM="${RT_SENTENCE_STREAM:-1}"

# ── CUDA kutubxonalari (bundle qilingan muhit ichidan, versiyadan mustaqil) ──
NVIDIA_ROOT=$(echo "$ENV_DIR"/lib/python*/site-packages/nvidia 2>/dev/null | awk '{print $1}')
if [ -d "$NVIDIA_ROOT" ]; then
    for _d in "$NVIDIA_ROOT"/*/lib; do
        [ -d "$_d" ] && export LD_LIBRARY_PATH="$_d:${LD_LIBRARY_PATH:-}"
    done
fi
export LD_LIBRARY_PATH="$ENV_DIR/lib:${LD_LIBRARY_PATH:-}"

# ── ffmpeg (kod oddiy "ffmpeg" deb chaqiradi) — env bin PATH boshiga ──
# NVENC'li ffmpeg (envs/ffmpeg-nvenc/) mavjud bo'lsa, uni BIRINCHI qo'yamiz —
# GPU enkod (h264_nvenc) avtomatik tanlanadi (libx264'dan ~5x tez, ayniqsa HD render).
if [ -x "$ROOT/envs/ffmpeg-nvenc/ffmpeg" ]; then
    export PATH="$ROOT/envs/ffmpeg-nvenc:$ENV_DIR/bin:${PATH:-}"
else
    export PATH="$ENV_DIR/bin:${PATH:-}"
fi

# ── .env dan OPENAI_API_KEY (config.py ham o'qiydi; bo'lmasa boot uchun dummy) ──
ENV_FILE="$BASE/.env"
if [ -f "$ENV_FILE" ]; then
    set -a; . "$ENV_FILE"; set +a
fi
if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "OGOHLANTIRISH: OPENAI_API_KEY yo'q — server ishga tushadi, lekin chat ishlamaydi."
    echo "                Chat uchun $ENV_FILE ichiga OPENAI_API_KEY yozing."
    export OPENAI_API_KEY="sk-dummy-for-boot"
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8100}"

# ── HTTPS (mikrofon LAN'dan ishlashi uchun SHART: brauzer getUserMedia'ni
#    faqat HTTPS yoki localhost'da beradi). certs/ mavjud bo'lsa avtomatik yoqiladi.
#    O'chirish: HTTPS=0 bash run.sh ──
SSL_ARGS=()
SCHEME="http"
CERT="$BASE/certs/cert.pem"
KEY="$BASE/certs/key.pem"
if [ "${HTTPS:-1}" != "0" ] && [ -f "$CERT" ] && [ -f "$KEY" ]; then
    SSL_ARGS=(--ssl-certfile "$CERT" --ssl-keyfile "$KEY")
    SCHEME="https"
fi

echo "============================================"
echo "  Avatar Studio backend"
echo "  Muhit : $ENV_DIR"
echo "  Public : $SCHEME://localhost:$PORT/           (ovozli suhbat, loginsiz)"
echo "  Admin  : $SCHEME://localhost:$PORT/admin      (panel, login)"
echo "  Studio : $SCHEME://localhost:$PORT/admin/studio"
if [ "$SCHEME" = "https" ]; then
    echo "  HTTPS  : YOQILGAN (mikrofon LAN'da ishlaydi; o'z-imzoli sertifikat — brauzer ogohlantirishini qabul qiling)"
fi
echo "============================================"

cd "$BASE"
exec "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT" --app-dir "$BASE" "${SSL_ARGS[@]}"

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

# ── CUDA kutubxonalari (bundle qilingan muhit ichidan, versiyadan mustaqil) ──
NVIDIA_ROOT=$(echo "$ENV_DIR"/lib/python*/site-packages/nvidia 2>/dev/null | awk '{print $1}')
if [ -d "$NVIDIA_ROOT" ]; then
    for _d in "$NVIDIA_ROOT"/*/lib; do
        [ -d "$_d" ] && export LD_LIBRARY_PATH="$_d:${LD_LIBRARY_PATH:-}"
    done
fi
export LD_LIBRARY_PATH="$ENV_DIR/lib:${LD_LIBRARY_PATH:-}"

# ── ffmpeg (kod oddiy "ffmpeg" deb chaqiradi) — env bin PATH boshiga ──
export PATH="$ENV_DIR/bin:${PATH:-}"

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
echo "============================================"
echo "  Avatar Studio backend"
echo "  Muhit : $ENV_DIR"
echo "  URL    : http://localhost:$PORT"
echo "  Studio : http://localhost:$PORT/studio"
echo "============================================"

cd "$BASE"
exec "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT" --app-dir "$BASE"

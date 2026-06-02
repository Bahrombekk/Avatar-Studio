#!/usr/bin/env bash
# ============================================================
#  Avatar Studio — portativ o'rnatish skripti.
#  Yangi kompyuterga papkani ko'chirgach BIR MARTA ishga tushiring:
#      bash setup.sh
#
#  Talablar (majburiy):
#    - Linux yoki Windows + WSL2 (Ubuntu)
#    - NVIDIA GPU + drayver (nvidia-smi ishlashi kerak)
#    - tar, bash
#  Eslatma: muhit Linux x86_64 + CUDA uchun qurilgan. Mac/oddiy Windows/
#  GPU'siz kompyuterda ISHLAMAYDI.
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="$ROOT/envs/avatar"
# Arxiv .tar (siqilmagan) yoki .tar.gz bo'lishi mumkin — qaysi bo'lsa shuni topamiz.
if [ -f "$ROOT/envs/avatar_env.tar" ]; then
  ENV_TAR="$ROOT/envs/avatar_env.tar"
else
  ENV_TAR="$ROOT/envs/avatar_env.tar.gz"
fi

echo "============================================"
echo "  Avatar Studio o'rnatish"
echo "  Loyiha ildizi: $ROOT"
echo "============================================"

# 0) GPU borligini ogohlantirish darajasida tekshirish
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "==> NVIDIA GPU topildi."
else
  echo "OGOHLANTIRISH: nvidia-smi topilmadi. Pipeline GPU talab qiladi —"
  echo "                GPU'siz mashinada inference ishlamaydi."
fi

# 1) Conda muhitini ochish (agar hali ochilmagan bo'lsa)
if [ -x "$ENV_DIR/bin/python" ]; then
  echo "==> Muhit allaqachon mavjud: $ENV_DIR (qayta ochilmaydi)"
else
  if [ ! -f "$ENV_TAR" ]; then
    echo "XATO: muhit arxivi topilmadi: $ENV_TAR"
    exit 1
  fi
  echo "==> Muhit arxivini ochish ($ENV_TAR, biroz kutadi)..."
  mkdir -p "$ENV_DIR"
  tar -xf "$ENV_TAR" -C "$ENV_DIR"   # -xf gzip'ni avtomatik aniqlaydi
  echo "==> Yo'llarni shu joyga moslash (conda-unpack)..."
  "$ENV_DIR/bin/python" "$ENV_DIR/bin/conda-unpack"
  echo "==> Muhit tayyor."
fi

# 1c) Qo'shimcha wheel'lar (offline) — LivePortrait idle generatsiya uchun
#     pykalman kabi paketlar. Arxivda yo'q; numpy'ga tegmaslik uchun --no-deps.
if ls "$ROOT"/envs/wheels/*.whl >/dev/null 2>&1; then
  for whl in "$ROOT"/envs/wheels/*.whl; do
    pkg=$(basename "$whl" | cut -d- -f1)
    if "$ENV_DIR/bin/python" -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$pkg') else 1)" 2>/dev/null; then
      continue   # allaqachon o'rnatilgan
    fi
    echo "==> Wheel o'rnatilmoqda (offline): $(basename "$whl")"
    "$ENV_DIR/bin/python" -m pip install --no-deps --no-index "$whl" || \
      echo "OGOHLANTIRISH: $(basename "$whl") o'rnatilmadi — idle generatsiya ishlamasligi mumkin."
  done
fi

# 1b) ffmpeg: imageio-ffmpeg bundlangan binarini bin/ffmpeg sifatida ulash
#     (kod oddiy "ffmpeg" deb chaqiradi — PATH'da bo'lishi kerak)
if [ ! -e "$ENV_DIR/bin/ffmpeg" ]; then
  FF=$(ls "$ENV_DIR"/lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-* 2>/dev/null | head -1 || true)
  if [ -n "${FF:-}" ]; then
    ln -sf "$FF" "$ENV_DIR/bin/ffmpeg"
    chmod +x "$FF" 2>/dev/null || true
    echo "==> ffmpeg ulandi (bundle): $FF"
  else
    echo "OGOHLANTIRISH: ffmpeg topilmadi. Tizimga o'rnating: apt install ffmpeg"
  fi
fi

# 2) .env tekshirish
if [ ! -f "$ROOT/backend/.env" ] && [ -f "$ROOT/backend/.env.example" ]; then
  echo "==> backend/.env yo'q — namuna nusxalanmoqda."
  cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
  echo "    Chat uchun backend/.env ichida OPENAI_API_KEY ni to'ldiring."
fi

echo ""
echo "============================================"
echo "  Tayyor! Ishga tushirish:"
echo "      bash backend/run.sh"
echo "  So'ng brauzerda: http://localhost:8100/studio"
echo "============================================"

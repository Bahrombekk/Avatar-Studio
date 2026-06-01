#!/bin/bash
# ============================================================
#  LP-MuseTalk Avatar backend — FastAPI (paket: app.main:app)
#  Port 8100. Avatar: madina_lp
#  Foydalanish: bash run.sh
# ============================================================

# BASE = backend/ (shu skript joylashgan papka). MT_DIR = bundle ichidagi modellar.
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MT_DIR="${MT_DIR:-$(cd "$BASE/../models/MuseTalk" 2>/dev/null && pwd)}"
CONDA_ROOT="${CONDA_ROOT:-/home/user/miniconda3}"
PYTHON="$CONDA_ROOT/envs/musetalk/bin/python"
export MT_DIR

source $CONDA_ROOT/etc/profile.d/conda.sh
conda deactivate 2>/dev/null

# .env dan OPENAI_API_KEY (+ Yandex)
ENV_FILE="$BASE/.env"
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
fi
if [ -z "$OPENAI_API_KEY" ]; then
    echo "XATO: OPENAI_API_KEY topilmadi! $ENV_FILE ga yozing."
    exit 1
fi

# MuseTalk import uchun PYTHONPATH
export PYTHONPATH="$MT_DIR:${PYTHONPATH}"

# CUDA library yo'llari
NVIDIA_LIBS="$CONDA_ROOT/envs/musetalk/lib/python3.10/site-packages/nvidia"
if [ -d "$NVIDIA_LIBS" ]; then
    export LD_LIBRARY_PATH="$NVIDIA_LIBS/cudnn/lib:$NVIDIA_LIBS/cublas/lib:$NVIDIA_LIBS/cuda_runtime/lib:$NVIDIA_LIBS/cufft/lib:$NVIDIA_LIBS/curand/lib:$NVIDIA_LIBS/cusolver/lib:$NVIDIA_LIBS/cusparse/lib:$NVIDIA_LIBS/nvjitlink/lib:${LD_LIBRARY_PATH}"
fi

echo "============================================"
echo "  LP-MuseTalk Avatar backend"
echo "  URL    : http://localhost:8100"
echo "  Studio : http://localhost:8100/studio"
echo "  Env    : musetalk | Avatar: madina_lp"
echo "============================================"

# app-dir = backend/ (app.main:app shu yerdan topiladi).
# cwd MuseTalk relative-path uchun model yuklashda os.chdir(MT_DIR) bilan beriladi.
cd "$BASE"
$PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port 8100 --app-dir "$BASE"

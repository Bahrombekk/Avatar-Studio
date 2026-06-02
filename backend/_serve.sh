#!/bin/bash
# Avatar Studio backend'ni avatar env'da ishga tushirish (test uchun).
cd /mnt/c/Users/User/Desktop/Avatar_Studio/backend
export MT_DIR="$(cd ../models/MuseTalk && pwd)"
export PYTHONPATH="$MT_DIR:$PYTHONPATH"
export OPENAI_API_KEY="${OPENAI_API_KEY:-sk-dummy-for-boot-test}"
exec ~/miniconda3/envs/avatar/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8100 --app-dir "$PWD"

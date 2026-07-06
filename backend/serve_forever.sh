#!/usr/bin/env bash
# Avatar Studio backend — qulasa o'zini qayta ishga tushiruvchi o'ram (supervisor).
# run.sh qandaydir sabab bilan to'xtasa, 3s kutib qayta ishga tushiradi.
# To'liq ajratilgan holda ishga tushiring:
#   setsid bash backend/serve_forever.sh >> /tmp/avatar_backend.log 2>&1 < /dev/null &
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # backend/
while true; do
    echo "[serve_forever] $(date '+%F %T') — backend ishga tushmoqda"
    bash "$BASE/run.sh"
    code=$?
    echo "[serve_forever] $(date '+%F %T') — backend to'xtadi (exit=$code), 3s dan keyin qayta..."
    sleep 3
done

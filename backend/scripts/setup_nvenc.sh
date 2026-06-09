#!/usr/bin/env bash
# NVENC'li static ffmpeg yuklab, envs/ffmpeg-nvenc/ ga o'rnatadi va sinaydi.
# run.sh uni avtomatik PATH boshiga qo'yadi → h264_nvenc enkod (HD render ~5x tez).
# Ishlatish:  bash backend/scripts/setup_nvenc.sh
set -e
# ROOT — skript joylashuviga nisbatan (backend/scripts/ -> loyiha ildizi).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="$ROOT/envs/ffmpeg-nvenc"
TMP="/tmp/ffmpeg-nvenc-dl"
mkdir -p "$TMP" "$DEST"
cd "$TMP"

echo ">>> Yuklanmoqda (BtbN gpl static — nvenc bilan)..."
wget -q --show-progress -O ff.tar.xz "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz" 2>&1 | tail -2 || {
  echo "wget xato"; exit 1; }
echo ">>> Ochilmoqda..."
tar xf ff.tar.xz
D=$(find . -maxdepth 1 -type d -name "ffmpeg-*" | head -1)
cp "$D/bin/ffmpeg" "$D/bin/ffprobe" "$DEST/"
chmod +x "$DEST/ffmpeg" "$DEST/ffprobe"

echo ">>> Versiya:"
"$DEST/ffmpeg" -hide_banner -version | head -1
echo ">>> NVENC encoderlar:"
"$DEST/ffmpeg" -hide_banner -encoders 2>/dev/null | grep -i nvenc || echo "  NVENC YO'Q!"
echo ">>> libx264 / aac bor-yo'qligi:"
"$DEST/ffmpeg" -hide_banner -encoders 2>/dev/null | grep -E "libx264|aac " | head

echo ">>> Haqiqiy NVENC kodlash testi (GPU)..."
"$DEST/ffmpeg" -y -v error -f lavfi -i testsrc=duration=1:size=1280x720:rate=25 \
  -c:v h264_nvenc -preset p5 -f mp4 /tmp/nvenc_test.mp4 && \
  echo "  ✓ NVENC ISHLAYDI: $(stat -c%s /tmp/nvenc_test.mp4) bayt" || \
  echo "  ✗ NVENC ishlamadi (GPU/driver?)"

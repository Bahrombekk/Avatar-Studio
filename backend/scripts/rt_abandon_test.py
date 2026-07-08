"""Tashlab ketilgan oqim testi: stream'ni ochib ~0.5s o'qib UZIB tashlaydi
(sahifa yangilagan foydalanuvchi kabi) — keyin server o'zini tozalashi shart
(ffmpeg o'ladi, GPU slot bo'shaydi). rt_profile_ttff.py bilan juft ishlatiladi."""
import asyncio
import json
import ssl
import sys
import time
import urllib.request

PCM_PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/test16k.pcm"
WS_URL = "wss://localhost:8100/api/realtime/ws"
BASE = "https://localhost:8100"
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


async def main():
    import websockets
    pcm = open(PCM_PATH, "rb").read()
    async with websockets.connect(WS_URL, max_size=None, ssl=_SSL) as ws:
        await ws.send("start")
        for i in range(0, len(pcm), 3200):
            await ws.send(pcm[i:i + 3200])
            await asyncio.sleep(0.01)
        await ws.send("stop")
        url = None
        while True:
            ev = json.loads(await asyncio.wait_for(ws.recv(), timeout=90))
            if ev.get("type") == "stream":
                url = ev["url"]
                break
            if ev.get("type") in ("done", "error"):
                break
        if not url:
            print("stream kelmadi ❌")
            return
        req = urllib.request.urlopen(BASE + url, timeout=30, context=_SSL)
        got = len(req.fp.read1(65536))
        time.sleep(0.5)
        req.close()          # ← MIJOZ KETDI (yarim yo'lda uzildi)
        print(f"UZILDI: {got} bayt o'qib tashlab ketildi (ataylab)")
    # WS ham yopildi — server endi hammasini tozalashi kerak.


asyncio.run(main())

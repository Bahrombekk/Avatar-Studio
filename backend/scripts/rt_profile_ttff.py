"""TTFF chuqur profillash (HTTPS server, port 8100).

rt_smoke_test.py'ning kengaytirilgani: wss/https (o'z-imzoli sert OK) +
video oqimidagi fMP4 qutilarini kuzatib ANIQ vaqtlarni chiqaradi:
  - init segment (ftyp+moov) — ffmpeg ishga tushdi
  - 1-moof — birinchi video fragment (brauzer o'ynashni boshlashi mumkin)
  - 2-moof — barqaror oqim
Server logidagi [TTFF] qatorlar bilan birga o'qiladi (RT_STREAM_PROFILE=1).

Ishga tushirish (WSL):
  envs/avatar/bin/python backend/scripts/rt_profile_ttff.py [/tmp/test16k.pcm]
"""
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
    try:
        import websockets
    except ImportError:
        print("XATO: websockets kutubxonasi yo'q")
        sys.exit(2)

    pcm = open(PCM_PATH, "rb").read()
    print(f"PCM: {len(pcm)} bayt (~{len(pcm)/32000:.1f}s)")

    async with websockets.connect(WS_URL, max_size=None, ssl=_SSL) as ws:
        await ws.send("start")
        step = 3200  # 100ms @16k
        for i in range(0, len(pcm), step):
            await ws.send(pcm[i:i + step])
            await asyncio.sleep(0.01)
        await ws.send("stop")
        t0 = time.time()
        stream_url = None
        t_stream = None
        first_token = None
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=90)
            ev = json.loads(msg)
            ts = round(time.time() - t0, 2)
            et = ev.get("type")
            if et == "token":
                if first_token is None:
                    first_token = ts
                    print(f"[{ts:6.2f}s] birinchi GPT token")
                continue
            info = ev.get("text") or ev.get("url") or ev.get("message") or ""
            print(f"[{ts:6.2f}s] {et}: {str(info)[:90]}")
            if et == "stream":
                stream_url = ev["url"]
                t_stream = ts
                break        # darrov videoga o'tamiz (brauzer ham shunday qiladi)
        if not stream_url:
            print("NATIJA: stream kelmadi ❌")
            sys.exit(1)

        # Video oqimi — brauzer kabi DARROV ochamiz, moof qutilarini kuzatamiz.
        t1 = time.time()
        req = urllib.request.urlopen(BASE + stream_url, timeout=120, context=_SSL)
        buf = b""
        got_init = None
        moofs = []
        total = 0
        while True:
            b = req.fp.read1(65536) if hasattr(req, "fp") else req.read(32768)
            if not b:
                break
            total += len(b)
            buf += b
            now = time.time() - t1
            if got_init is None and b"moov" in buf:
                got_init = now
                print(f"  init segment (moov): +{now:.2f}s")
            # moof qutilarini sanaymiz (faqat dastlabki 3 tasi qiziq)
            while len(moofs) < 3:
                i = buf.find(b"moof")
                if i < 0:
                    break
                moofs.append(now)
                print(f"  {len(moofs)}-moof (fragment): +{now:.2f}s")
                buf = buf[i + 4:]
            if len(moofs) >= 3:
                buf = b""   # boshqa qidirmaymiz, faqat o'qib tugatamiz
        t_all = time.time() - t1
        print(f"NATIJA: stream eventi {t_stream}s (stop'dan); "
              f"1-fragment +{moofs[0]:.2f}s" if moofs else "fragment YO'Q ❌",
              f"| jami {total/1e6:.1f} MB ({t_all:.1f}s)")
        # WS'dagi qolgan eventlarni ham o'qib chiqamiz (done kutish shart emas)


asyncio.run(main())

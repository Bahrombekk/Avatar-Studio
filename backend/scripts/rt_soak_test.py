"""SOAK-TEST: N marta ketma-ket "gapirtirish" — barqarorlik tekshiruvi.

Har sikl: WS orqali PCM yuboriladi → transcript → stream → video TO'LIQ o'qiladi.
Klassifikatsiya:
  OK          — oqim tugadi (EOF), yetarli bayt keldi
  NO_STREAM   — stream eventi kelmadi (GPT/TTS oldin yiqildi)
  STALL       — oqim o'rtada qotdi (per-read timeout) → "chala javob"
  EMPTY       — oqim ochildi-yu, juda kam bayt kelib tugadi
Har 7-sikl ATAYLAB tashlab ketiladi (brauzer refresh imitatsiyasi) — keyingi
sikl baribir ishlashi shart. Xatoda /proc diagnostikasi chiqariladi.

Ishga tushirish:
  envs/avatar/bin/python backend/scripts/rt_soak_test.py [N] [pcm_yoli]
"""
import asyncio
import json
import ssl
import subprocess
import sys
import time
import urllib.request

N = int(sys.argv[1]) if len(sys.argv) > 1 else 50
PCM_PATH = sys.argv[2] if len(sys.argv) > 2 else "/tmp/test16k.pcm"
WS_URL = "wss://localhost:8100/api/realtime/ws"
BASE = "https://localhost:8100"
READ_TIMEOUT = 25       # bitta read uchun (oqim shuncha jim qolsa = STALL)
TOTAL_TIMEOUT = 120     # butun javob uchun
ABANDON_EVERY = 7       # har 7-sikl tashlab ketiladi

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def diag(tag):
    """Xato paytidagi jarayon holati (ffmpeg wchan'lari)."""
    try:
        out = []
        pids = subprocess.run(["pgrep", "ffmpeg"], capture_output=True, text=True
                              ).stdout.split()
        for p in pids:
            try:
                w = open(f"/proc/{p}/wchan").read()
                out.append(f"ffmpeg {p}:{w}")
            except OSError:
                pass
        print(f"    [diag {tag}] {'; '.join(out) or 'ffmpeg yo`q'}")
    except Exception as e:  # noqa: BLE001
        print(f"    [diag xato] {e}")


async def one_cycle(i, pcm, abandon=False):
    t0 = time.time()
    try:
        import websockets
        async with websockets.connect(WS_URL, max_size=None, ssl=_SSL,
                                      open_timeout=15) as ws:
            await ws.send("start")
            for j in range(0, len(pcm), 3200):
                await ws.send(pcm[j:j + 3200])
                await asyncio.sleep(0.008)
            await ws.send("stop")
            url = None
            err = None
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=45)
                except asyncio.TimeoutError:
                    return ("NO_STREAM", "WS event 45s kutildi", time.time() - t0)
                ev = json.loads(msg)
                et = ev.get("type")
                if et == "stream":
                    url = ev["url"]
                    break
                if et == "error":
                    err = ev.get("message", "?")
                    break
                if et == "done":
                    break
            if not url:
                return ("NO_STREAM", err or "stream kelmadi", time.time() - t0)

            # Video oqimini brauzer kabi o'qiymiz (WS OCHIQ qoladi!).
            t1 = time.time()
            total = 0
            loop = asyncio.get_event_loop()
            req = await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(BASE + url, timeout=READ_TIMEOUT,
                                                     context=_SSL))
            try:
                if abandon:
                    b = await loop.run_in_executor(None, req.fp.read1, 65536)
                    total += len(b)
                    await asyncio.sleep(0.5)
                    req.close()
                    return ("ABANDON", f"{total}B o'qib uzildi", time.time() - t0)
                while True:
                    if time.time() - t1 > TOTAL_TIMEOUT:
                        return ("STALL", f"TOTAL>{TOTAL_TIMEOUT}s ({total}B)",
                                time.time() - t0)
                    try:
                        b = await asyncio.wait_for(
                            loop.run_in_executor(None, req.fp.read1, 65536),
                            timeout=READ_TIMEOUT)
                    except asyncio.TimeoutError:
                        return ("STALL", f"read>{READ_TIMEOUT}s jim ({total}B keldi)",
                                time.time() - t0)
                    if not b:
                        break
                    total += len(b)
            finally:
                try:
                    req.close()
                except Exception:
                    pass
            if total < 100_000:
                return ("EMPTY", f"faqat {total}B", time.time() - t0)
            return ("OK", f"{total/1e6:.1f}MB", time.time() - t0)
    except Exception as e:  # noqa: BLE001
        return ("ERROR", f"{type(e).__name__}: {str(e)[:80]}", time.time() - t0)


async def main():
    pcm = open(PCM_PATH, "rb").read()
    print(f"SOAK: {N} sikl, PCM {len(pcm)/32000:.1f}s, har {ABANDON_EVERY}-sikl tashlab ketiladi\n")
    stats = {}
    fails = []
    for i in range(1, N + 1):
        abandon = (i % ABANDON_EVERY == 0)
        st, info, dt = await one_cycle(i, pcm, abandon)
        stats[st] = stats.get(st, 0) + 1
        mark = "✅" if st in ("OK", "ABANDON") else "❌"
        print(f"[{i:02d}/{N}] {mark} {st:9s} {dt:5.1f}s  {info}")
        if st not in ("OK", "ABANDON"):
            fails.append((i, st, info))
            diag(f"sikl {i}")
        await asyncio.sleep(0.4)
    print("\n=== YAKUN ===")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    if fails:
        print(f"\nXATOLAR ({len(fails)}):")
        for i, st, info in fails:
            print(f"  sikl {i}: {st} — {info}")
        sys.exit(1)
    print("\nHAMMASI TOZA ✅")


asyncio.run(main())

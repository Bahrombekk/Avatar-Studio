"""Jonli temir yo'l ma'lumoti — eticket.railway.uz (rasmiy sayt) API'si orqali.

Narx, jadval (qachon qatnaydi), bilet turlari, bo'sh joylar — REAL VAQTDA.
API XSRF/sessiya talab qiladi (oddiy so'rov 403), shuning uchun Playwright (headless
Chromium) bitta uzun-yashovchi sessiya ochib turadi va API'ni shu sessiya orqali
chaqiradi. Brauzer ALOHIDA worker-thread'da yashaydi (Playwright sync API talabi).

GPT integratsiyasi: railway_context(user_text) — savol poyezd/chipta haqida bo'lsa,
GPT bilan (qayerdan/qayerga/sana) ajratiladi, jonli qidiriladi va natija system
prompt'ga "MA'LUMOT" bloki sifatida qo'shiladi (gpt.py shu bilan asoslangan javob beradi).

Xato/yo'q bo'lsa "" qaytaradi → suhbat avvalgidek davom etadi (degradatsiya).
"""
import datetime
import json
import logging
import queue
import threading
import time

log = logging.getLogger(__name__)

BASE = "https://eticket.railway.uz"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/148.0 Safari/537.36")

# Brauzer ichida bajariladigan fetch (XSRF cookie'dan header oladi, sessiya bilan).
_JS_POST = """
async (args) => {
  const [url, body] = args;
  const m = document.cookie.match(/XSRF-TOKEN=([^;]+)/);
  const h = {'Accept':'application/json','Content-Type':'application/json'};
  if (m) h['X-XSRF-TOKEN'] = decodeURIComponent(m[1]);
  const r = await fetch(url, {method:'POST', headers:h, credentials:'include', body: JSON.stringify(body)});
  return {status: r.status, text: await r.text()};
}
"""

_req_q: queue.Queue = queue.Queue()
_started = False
_lock = threading.Lock()

# Brauzer sessiyasini proaktiv yangilash (idle'dan keyin kafolatli bekor round-trip
# bo'lmasligi uchun). Reaktiv (401/403/419) yangilash baribir saqlanadi.
_SESSION_MAX_AGE = 1200          # 20 daqiqa

# ── Natija keshi (har savol brauzerga bormasin) ──
# Stansiya kodi deyarli o'zgarmaydi → uzoq TTL. Poyezd narx/joy o'zgaruvchan →
# qisqa TTL (jonliligini saqlash bilan saytga yukni kamaytirish orasidagi muvozanat).
_STATION_TTL = 24 * 3600         # 24 soat
_SEARCH_TTL = 90                 # 90 soniya
_CACHE_MAX = 500
_station_cache: dict = {}
_search_cache: dict = {}
_cache_lock = threading.Lock()


def _cache_get(store: dict, key, ttl: float):
    """Kesh elementi (yangiligi TTL ichida bo'lsa) yoki None. Eskisini tozalaydi."""
    with _cache_lock:
        e = store.get(key)
        if e is not None:
            ts, value = e
            if (time.time() - ts) < ttl:
                return value
            store.pop(key, None)
    return None


def _cache_put(store: dict, key, value) -> None:
    with _cache_lock:
        store[key] = (time.time(), value)
        if len(store) > _CACHE_MAX:
            oldest = min(store, key=lambda k: store[k][0])
            store.pop(oldest, None)


def clear_cache() -> None:
    """Stansiya + qidiruv keshini tozalaydi (admin /cache/clear va testlar uchun)."""
    with _cache_lock:
        _station_cache.clear()
        _search_cache.clear()


# ── Brauzer worker-thread (Playwright sync — bitta thread'da yashashi shart) ──
def _worker():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        log.error("[railway] playwright yo'q: %s", e)
        return
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = browser.new_context(locale="ru-RU", user_agent=_UA)
            page = ctx.new_page()

            def _refresh():
                # domcontentloaded — networkidle SPA'da (analytics/stripe doimiy ulanish)
                # ko'pincha timeout bo'ladi. XSRF cookie dastlabki javob/XHR'da o'rnatiladi,
                # shuning uchun qisqa kutish yetarli.
                try:
                    page.goto(BASE + "/ru/pages/trains-page", wait_until="domcontentloaded", timeout=30000)
                except Exception as e:  # noqa: BLE001
                    log.warning("[railway] goto: %s", e)
                page.wait_for_timeout(2500)   # csrf-token XHR cookie o'rnatishi uchun

            _refresh()
            last_refresh = [time.time()]
            log.info("[railway] brauzer sessiyasi tayyor")

            def _do_refresh():
                _refresh()
                last_refresh[0] = time.time()

            def _post(url, body):
                # Proaktiv: uzoq idle'dan keyin sessiyani oldindan yangilaymiz.
                if (time.time() - last_refresh[0]) > _SESSION_MAX_AGE:
                    _do_refresh()
                r = page.evaluate(_JS_POST, [url, body])
                if r.get("status") in (401, 403, 419):     # sessiya eskirdi → yangilab qayta
                    _do_refresh()
                    r = page.evaluate(_JS_POST, [url, body])
                return r

            while True:
                item = _req_q.get()
                if item is None:
                    break
                kind, args, holder, ev = item
                try:
                    if kind == "resolve":
                        r = _post(BASE + "/api/v1/handbook/stations/list", {"name": args[0]})
                    else:  # search
                        dep, arv, date = args
                        r = _post(BASE + "/api/v3/handbook/trains/list",
                                  {"directions": {"forward": {"date": date,
                                   "depStationCode": dep, "arvStationCode": arv}}})
                    holder["result"] = json.loads(r["text"]) if r.get("status") == 200 else None
                    holder["status"] = r.get("status")
                except Exception as e:  # noqa: BLE001
                    holder["error"] = str(e)
                finally:
                    ev.set()
    except Exception as e:  # noqa: BLE001
        log.error("[railway] worker to'xtadi: %s", e)
    finally:
        global _started
        with _lock:
            _started = False


def _ensure_worker():
    global _started
    with _lock:
        if _started:
            return
        threading.Thread(target=_worker, daemon=True).start()
        _started = True


def _call(kind, *args, timeout=50):
    _ensure_worker()
    holder, ev = {}, threading.Event()
    _req_q.put((kind, args, holder, ev))
    if not ev.wait(timeout):
        log.warning("[railway] %s timeout", kind)
        return None
    if holder.get("error"):
        log.warning("[railway] %s xato: %s", kind, holder["error"])
    return holder.get("result")


def warmup():
    """Startupda brauzer sessiyasini oldindan ochish (birinchi savol tez bo'lsin)."""
    try:
        _call("resolve", "tosh", timeout=60)
    except Exception:  # noqa: BLE001
        pass


def shutdown() -> None:
    """Worker thread'ni xushmuomala to'xtatish (sentinel → brauzer yopiladi)."""
    global _started
    with _lock:
        if not _started:
            return
    _req_q.put(None)


# ── Stansiya nomi → kod ──
def resolve_station(name: str):
    """Shahar/stansiya nomidan kod topadi (O'zbekiston stansiyalari afzal).
    Natija uzoq TTL bilan keshlanadi (stansiya kodi deyarli o'zgarmaydi)."""
    name = (name or "").strip()
    if not name:
        return None
    key = name.lower()[:24]
    cached = _cache_get(_station_cache, key, _STATION_TTL)
    if cached is not None:
        return cached
    data = _call("resolve", name[:24])
    stations = ((data or {}).get("data") or {}).get("stations") or []
    if not stations:
        return None                     # topilmadi/xato — keshlamaymiz (qayta urinish)
    # O'zbekiston kodlari "29" bilan boshlanadi — ularni afzal ko'ramiz.
    uz = [s for s in stations if str(s.get("code", "")).startswith("29")]
    pool = uz or stations
    up = name.upper()
    exact = [s for s in pool if s.get("name", "").upper() == up]
    chosen = (exact or pool)[0]
    result = {"code": str(chosen["code"]), "name": chosen.get("name", name)}
    _cache_put(_station_cache, key, result)
    return result


# ── Poyezd qidirish ──
def search_trains(dep_code: str, arv_code: str, date: str):
    """Yo'nalish+sana bo'yicha poyezdlar. Qisqa TTL bilan keshlanadi (narx/joy
    o'zgaruvchan, lekin 90s ichida saytni qayta urmaymiz)."""
    key = (dep_code, arv_code, date)
    cached = _cache_get(_search_cache, key, _SEARCH_TTL)
    if cached is not None:
        return cached
    data = _call("search", dep_code, arv_code, date)
    if data is None:
        return []                       # transient xato — keshlamaymiz
    fwd = ((data.get("data") or {}).get("directions") or {}).get("forward") or {}
    trains = fwd.get("trains") or []
    _cache_put(_search_cache, key, trains)
    return trains


# ── Niyat (intent) — savol poyezd/chipta haqidami? ──
_KEYWORDS = (
    "poyezd", "poezd", "поезд", "train", "chipta", "bilet", "билет", "ticket",
    "afrosiyob", "afrosiyo", "shark", "sharq", "narx", "narxi", "qancha", "цена",
    "jadval", "qatna", "reys", "vagon", "joy", "o'rin", "o‘rin",
)


def looks_like_train_query(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in _KEYWORDS)


def _extract_params(user_text: str, language: str):
    """GPT (function-calling) bilan (qayerdan/qayerga/sana) ni ajratadi.
    Sana YYYY-MM-DD; nisbiy ("ertaga","bugun") bugungi sanaga nisbatan."""
    from app.services.gpt import client
    today = datetime.date.today().isoformat()
    tools = [{
        "type": "function",
        "function": {
            "name": "poyezd_qidir",
            "description": "Foydalanuvchi temir yo'l chiptasi/poyezd narxi yoki jadvali "
                           "haqida so'rasa shu chaqiriladi.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_city": {"type": "string", "description": "Jo'nash shahri/stansiyasi"},
                    "to_city": {"type": "string", "description": "Borish shahri/stansiyasi"},
                    "date": {"type": "string",
                             "description": f"Sana YYYY-MM-DD. Bugun {today}. "
                                            "Aytilmasa yoki 'bugun' bo'lsa shu sana, 'ertaga' +1 kun."},
                },
                "required": ["from_city", "to_city"],
            },
        },
    }]
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini", temperature=0,
            messages=[{"role": "user", "content": user_text}],
            tools=tools, tool_choice="auto", max_tokens=120,
        )
        calls = resp.choices[0].message.tool_calls
        if not calls:
            return None
        args = json.loads(calls[0].function.arguments)
        if not args.get("from_city") or not args.get("to_city"):
            return None
        args["date"] = args.get("date") or today
        return args
    except Exception as e:  # noqa: BLE001
        log.warning("[railway] extract xato: %s", e)
        return None


def _fmt_date(d: str) -> str:
    return d


def _format(params: dict, trains: list, dep_name: str, arv_name: str) -> str:
    """Topilgan poyezdlarni system-prompt uchun MA'LUMOT bloki qiladi."""
    date = params.get("date", "")
    head = (f"JONLI TEMIR YO'L MA'LUMOTI ({dep_name} → {arv_name}, {date}) — "
            f"FAQAT shu ma'lumotga tayan, narxlarni o'zgartirma, so'mda ayt:")
    if not trains:
        return head + f"\n- Bu sana/yo'nalishda poyezd topilmadi."
    lines = [head]
    for tr in trains[:6]:
        num = tr.get("number", "")
        brand = tr.get("brand") or tr.get("type", "")
        dep_t = tr.get("departureDate", "")
        arr_t = tr.get("arrivalDate", "")
        dur = tr.get("timeOnWay", "")
        cars = tr.get("cars") or []
        cls = []
        for c in cars:
            for tf in (c.get("tariffs") or []):
                price = tf.get("tariff")
                stype = tf.get("classServiceType", "")
                free = tf.get("freeSeats", "")
                if price:
                    cls.append(f"{stype}: {int(price):,} so'm ({free} joy)".replace(",", " "))
        cls_s = "; ".join(cls[:5]) if cls else "joylar/narx ko'rsatilmagan (bo'sh joy yo'q bo'lishi mumkin)"
        lines.append(f"- {brand} {num}: jo'nash {dep_t}, yetib borish {arr_t} (yo'l {dur}). {cls_s}")
    return "\n".join(lines)


def railway_context(user_text: str, language: str = "uz") -> str:
    """Asosiy kirish: savol poyezd haqida bo'lsa, jonli ma'lumot blokini qaytaradi.
    Aks holda/xatoda "" (suhbat avvalgidek davom etadi)."""
    if not looks_like_train_query(user_text):
        return ""
    try:
        params = _extract_params(user_text, language)
        if not params:
            return ""
        dep = resolve_station(params["from_city"])
        arv = resolve_station(params["to_city"])
        if not dep or not arv:
            return ""
        trains = search_trains(dep["code"], arv["code"], params["date"])
        return _format(params, trains, dep["name"], arv["name"])
    except Exception as e:  # noqa: BLE001
        log.warning("[railway] context xato: %s", e)
        return ""

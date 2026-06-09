# Avatar Studio — To'liq loyiha tuzilmasi

Jami hajm: **~12 GB** (modellar bilan birga).

> **Yangilanish (production hardening):** quyidagi daraxt asosiy tuzilmani ko'rsatadi,
> lekin keyingi qo'shimchalar ham bor:
> - **Frontend** endi **TypeScript** (`.tsx`/`.ts`; `App.jsx`/`main.jsx` o'rniga `main.tsx`,
>   `app/router.tsx`, `api/client.ts`).
> - **Backend yangi modullar:** `core/logging.py` (JSON log + request_id), `core/middleware.py`
>   (request-id + `/metrics`), `services/knowledge.py` (RAG bilim bazasi),
>   `services/conversations.py` (SQLite suhbat saqlash), `api/routes/{knowledge,conversations}.py`.
> - **Config:** `core/config.py` da `Settings` (pydantic-settings, validatsiyali).
> - **Testlar:** `backend/tests/` (pytest, yengil deps) + frontend `*.test.ts(x)` (vitest);
>   CI: `.github/workflows/ci.yml`.
> - **Deploy:** `Dockerfile` + `docker-compose.yml` (ilova qatlami).
> - Og'ir ML importlari (`musetalk`/`torch`) endi **lazy** — `create_app()` ularsiz import bo'ladi.

```
Avatar_Studio/
│
├── SETUP.md                      # O'rnatish va ishga tushirish qo'llanmasi
├── STRUCTURE.md                  # Shu fayl
├── README.md                     # Loyiha umumiy ko'rinishi
│
├── backend/                      # ── FastAPI paketi (port 8100) ──
│   │
│   ├── run.sh                    # Ishga tushirish (BASE/MT_DIR avtomatik)
│   ├── requirements.txt          # FastAPI/uvicorn/openai/edge-tts (yengil deps)
│   ├── .env                      # MAXFIY kalitlar (OpenAI, Yandex) — ulashilmaydi
│   ├── .env.example              # Kalitlar namunasi (ommaga shu ketadi)
│   │
│   ├── app/                      # ── Ilova paketi ──
│   │   ├── main.py               #   create_app() factory + lifespan warmup;
│   │   │                         #     router'lar, GET / , /videos, /studio mount
│   │   ├── core/
│   │   │   ├── config.py         #   .env / env-var yuklash, openai_api_key()
│   │   │   └── paths.py          #   MT_DIR, avatar artefakt yo'llari, FRONTEND_DIST
│   │   ├── api/
│   │   │   ├── deps.py           #   resolve(req) → (avatar, voice)
│   │   │   └── routes/
│   │   │       ├── chat.py       #   POST /chat, /chat-stream (SSE)
│   │   │       ├── avatars.py    #   /api/avatars CRUD
│   │   │       ├── analytics.py  #   GET /api/analytics
│   │   │       └── system.py     #   /voices, /idle.jpg, /health, /cache/*
│   │   ├── schemas/
│   │   │   └── chat.py           #   ChatRequest (pydantic)
│   │   └── services/
│   │       ├── pipeline.py       #   Oqim: GPT → TTS → MuseTalk → mp4
│   │       ├── gpt.py            #   GPT-4o-mini + system prompt
│   │       ├── tts.py            #   edge-TTS / Yandex v1 / v3 ovozlar
│   │       ├── musetalk.py       #   MuseTalk inference (madina_lp)
│   │       ├── avatar_store.py   #   JSON avatar CRUD + event log
│   │       └── cache.py          #   Javob/video keshlash
│   │
│   ├── data/                     # ── Per-avatar / per-voice saqlash ──
│   │   ├── registry.json         #   {"version":1,"avatars":[id,...]} (tartib)
│   │   └── avatars/<id>/         #   har avatar uchun alohida papka
│   │       ├── avatar.json       #     to'liq konfiguratsiya
│   │       ├── stats.json        #     {sessions,avgLatency,cacheRate,csat}
│   │       ├── events.jsonl      #     SHU avatar chat loglari
│   │       └── voices/<voice>/   #     har ovoz uchun alohida
│   │           ├── cache.json    #       shu avatar+ovoz kesh indeksi
│   │           └── videos/<eid>.mp4  #   kesh videolari (BIR marta saqlanadi)
│   ├── scripts/
│   │   └── migrate_storage.py    # Eski tekis JSON → yangi tuzilma migratsiya
│   └── static/
│       ├── index.html            # Oddiy chat sahifasi (zaxira)
│       └── idle.jpg              # Chat idle rasm
│
├── frontend/                     # ── Vite + React (base: /studio/) ──
│   │
│   ├── package.json              # react/react-dom + vite + @vitejs/plugin-react
│   ├── vite.config.js            # base /studio/, dev proksisi (5173 → 8100)
│   ├── index.html                # Vite kirish HTML + boot splash
│   ├── dist/                     # Build natijasi (backend /studio dan beradi)
│   └── src/
│       ├── main.jsx              #   ReactDOM root + CSS importlari + splash
│       ├── App.jsx               #   Router + tweaks (default export)
│       ├── api/client.js         #   Backend API klienti (fetch + SSE)
│       ├── data/constants.js     #   Ovozlar, tillar, fallback data
│       ├── lib/
│       │   ├── icons.jsx         #   SVG ikonkalar (I.*)
│       │   └── theme.js          #   Tema/shrift (applyTheme)
│       ├── components/
│       │   ├── AdminShell.jsx    #   Sidebar + Topbar + Dashboard
│       │   ├── ui/index.jsx      #   UI primitivlari (Btn, Card, ...)
│       │   └── tweaks/TweaksPanel.jsx  # Sozlash paneli + form-control'lar
│       ├── pages/
│       │   ├── ChatScreen.jsx    #   Real /chat-stream chat + video
│       │   ├── AvatarEditor.jsx  #   6 tabli avatar muharriri (CRUD)
│       │   └── Analytics.jsx     #   Latency/volume/cache grafiklar
│       └── styles/
│           ├── styles.css        #   Chat + umumiy stillar
│           └── admin.css         #   Admin panel stillari
│
└── models/                       # ── AI modellar (~11.4 GB) ──
    │
    ├── MuseTalk/                 # (9.3 GB) lip-sync repo + modellar
    │   ├── musetalk/             # Kutubxona kodi (utils, models)
    │   ├── models/               # ── Model og'irliklari (8.7 GB) ──
    │   │   ├── musetalkV15/      #   unet.pth + musetalk.json (asosiy)
    │   │   ├── sd-vae/           #   VAE enkoder/dekoder
    │   │   ├── whisper/          #   Audio feature
    │   │   ├── dwpose/           #   Poza aniqlash
    │   │   ├── face-parse-bisent/#   Yuz segmentatsiya
    │   │   └── syncnet/
    │   ├── results/v15/avatars/madina_lp/   # ── Avatar artefakti ──
    │   │   ├── full_imgs/        #   200 PNG kadr (idle yuz)
    │   │   ├── latents.pt        #   Oldindan hisoblangan latentlar
    │   │   ├── coords.pkl        #   Yuz koordinatalari
    │   │   ├── mask/ + mask_coords.pkl
    │   │   └── avator_info.json
    │   ├── configs/ assets/ scripts/
    │   └── requirements.txt
    │
    └── LivePortrait/             # (2.1 GB) idle kadr yaratish (runtime'da shart emas)
        ├── pretrained_weights/   #   2.0 GB model og'irliklari
        ├── inference.py
        └── assets/
```

## Oqim diagrammasi

```
  Foydalanuvchi (brauzer /studio)
        │  matn
        ▼
  api/routes/chat.py  /chat-stream (SSE)
        │
        ▼
  services/pipeline.py   (kesh = get_cache(avatar_id, voice))
   ├─ 1. GPT-4o-mini ──────────► javob matni      (event: text)
   ├─ 2. TTS (edge / Yandex) ──► WAV ovoz          (event: tts_done)
   └─ 3. MuseTalk + madina_lp ─► lip-sync mp4      (event: video)
        │
        ▼
  data/avatars/<id>/voices/<voice>/videos/<eid>.mp4
        │   (GET /videos/<id>/<voice>/<eid>.mp4)
        ▼
  ChatScreen <video>
        │
        ▼
  avatar_store.log_event() ──► data/avatars/<id>/events.jsonl ──► /api/analytics
```

## Komponentlar bog'liqligi

- **Conda muhiti** (`musetalk`, Python 3.10) — bundle'ga kirmaydi, qayta yaratiladi (SETUP.md §4).
- **Frontend dist** — `frontend/` da `npm run build` qilinadi; `main.py` uni `FRONTEND_DIST` (= `frontend/dist`) dan `/studio` ga mount qiladi.
- **MT_DIR** — `pipeline.py`/`musetalk.py` va `run.sh` `models/MuseTalk` ni avtomatik topadi; `MT_DIR` env bilan bekor qilsa bo'ladi.
- **realtime/** (port 8000, LatentSync) — bu loyihadan butunlay alohida, bundle'ga kirmaydi.
```

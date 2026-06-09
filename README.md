# Avatar Studio

LivePortrait idle + MuseTalk lip-sync asosidagi **gapiruvchi avatar** platformasi.
Foydalanuvchi matn yozadi → GPT javob beradi → ovoz sintez qilinadi → avatar
lab harakati bilan video qiladi.

```
matn → GPT-4o-mini → TTS (edge / Yandex) → MuseTalk (madina_lp) → mp4
```

## Tuzilma

| Papka | Vazifa |
|-------|--------|
| `backend/`  | FastAPI paketi (port **8100**) — pipeline, API, `/studio` mount |
| `frontend/` | Vite + React admin panel (base `/studio/`) |
| `models/`   | MuseTalk (~9.3 GB) + LivePortrait (~2.1 GB) modellari |

To'liq daraxt uchun → [STRUCTURE.md](STRUCTURE.md).

## Tezkor start

```bash
# 1. Frontend build
cd frontend && npm install && npm run build

# 2. Backend (WSL Ubuntu, musetalk conda muhiti)
cd ../backend
cp .env.example .env        # kalitlarni to'ldiring
bash run.sh
```

Brauzerda oching: **http://localhost:8100/studio**

To'liq qo'llanma → [SETUP.md](SETUP.md).

## Asosiy endpoint'lar

| Endpoint | Tavsif |
|----------|--------|
| `GET /studio`        | Admin panel (Vite + React + TypeScript build) |
| `POST /chat-stream`  | SSE oqimi: `text` → `tts_done` → `video` → `done` |
| `WS /api/realtime/ws`| Real-time ovozli suhbat (streaming STT → video) |
| `GET /api/avatars`   | Avatarlar CRUD |
| `… /api/avatars/{id}/knowledge` | **RAG bilim bazasi** (hujjat/FAQ → grounded javob) |
| `GET /api/conversations` | Saqlangan suhbat transkriptlari (SQLite) |
| `… /api/studio`, `/api/canned` | Video Studiya (offline HD) + Tayyor javoblar |
| `GET /api/analytics` | Real analitika (`events.jsonl` dan) |
| `GET /voices`        | Mavjud TTS ovozlari |
| `GET /health`        | Model/kalit/kesh holati |
| `GET /metrics`       | Process metrikalari (so'rov soni, p50/p95 latency, xato) |

Har so'rov `X-Request-ID` oladi va strukturali (JSON) log qatori yoziladi.

## Testlar va CI

```bash
# Backend (yengil deps — torch/musetalk SHART EMAS)
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest                       # ilova qatlami: auth, config, cache, RAG, suhbat, API

# Frontend
cd frontend
npm run typecheck && npm run lint && npm test && npm run build
```

CI: `.github/workflows/ci.yml` — har PR'da frontend + backend testlari (GPU'siz).

## Docker (ilova qatlami)

```bash
docker compose up --build       # → http://localhost:8100/studio
```

> To'liq GPU lip-sync inference og'ir ML bog'liqliklari + NVIDIA runtime + `models/`
> hajmini talab qiladi — `Dockerfile` izohlariga qarang. Bu image API/panel va
> torch'siz qismlarni beradi.

## Eslatmalar

- **Real avatar:** faqat `madina_lp` (oldindan tayyorlangan video artefakti).
  Yangi avatarlar uning yuzini ulashadi, lekin o'z ovozi/personasini oladi.
- `.env` faqat lokal — **hech qachon git'ga qo'shmang** (`.env.example` namuna).
- Conda muhiti (`musetalk`, Python 3.10) bundle'ga kirmaydi — qayta yaratiladi.
- Bu loyiha `realtime/` (port 8000, LatentSync) dan **mutlaqo alohida**.

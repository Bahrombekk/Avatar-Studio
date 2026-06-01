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
| `GET /studio`        | Admin panel (Vite build) |
| `POST /chat-stream`  | SSE oqimi: `text` → `tts_done` → `video` → `done` |
| `GET /api/avatars`   | Avatarlar CRUD |
| `GET /api/analytics` | Real analitika (`events.jsonl` dan) |
| `GET /voices`        | Mavjud TTS ovozlari |
| `GET /health`        | Model/kalit/kesh holati |

## Eslatmalar

- **Real avatar:** faqat `madina_lp` (oldindan tayyorlangan video artefakti).
  Yangi avatarlar uning yuzini ulashadi, lekin o'z ovozi/personasini oladi.
- `.env` faqat lokal — **hech qachon git'ga qo'shmang** (`.env.example` namuna).
- Conda muhiti (`musetalk`, Python 3.10) bundle'ga kirmaydi — qayta yaratiladi.
- Bu loyiha `realtime/` (port 8000, LatentSync) dan **mutlaqo alohida**.

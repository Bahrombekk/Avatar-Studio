# Avatar Studio — O'rnatish va ishga tushirish

LivePortrait idle + MuseTalk lip-sync asosidagi "gapiruvchi avatar" platformasi.
Oqim: **foydalanuvchi matni → GPT → TTS (edge/Yandex) → MuseTalk → mp4**.

- Backend port: **8100**
- Avatar (real video): **madina_lp**
- Admin panel: **http://localhost:8100/studio**

> Eslatma: bu loyiha `realtime/` (port 8000, LatentSync) dan **alohida**. Ikkalasini aralashtirmang.

---

## 1. Talablar

- Windows 11 + **WSL2** (Ubuntu distrosi)
- NVIDIA GPU + CUDA (MuseTalk uchun)
- **Miniconda** (`/home/user/miniconda3`)
- `musetalk` nomli conda muhiti (Python 3.10)
- ffmpeg
- **Node.js 18+** (frontend Vite build uchun — faqat ishlab chiqishda kerak)

## 2. Papka tuzilmasi

```
Avatar_Studio/
├── backend/         # FastAPI paketi (app/, run.sh, requirements.txt)
├── frontend/        # Vite + React manba (src/) → build qilinsa dist/
├── models/
│   ├── MuseTalk/      # MuseTalk repo + modellar + madina_lp avatar artefakti
│   └── LivePortrait/  # idle kadr yaratish uchun (runtime'da shart emas)
├── SETUP.md
├── STRUCTURE.md
└── README.md
```

## 3. Maxfiy kalitlar (.env)

`backend/.env.example` ni `backend/.env` nomi bilan nusxalab, qiymatlarni yozing:

```
OPENAI_API_KEY=sk-...
YX_API_KEY=...
YX_FOLDER_ID=...
```

> `.env` faylni hech qachon ulashmang yoki git'ga qo'shmang. Ommaga faqat `.env.example` ketadi.

## 4. Conda muhiti (ko'chirib bo'lmaydi — qayta yarating)

Conda muhiti absolyut yo'llar va CUDA kutubxonalariga bog'liq, shuning uchun u
bundle ichiga ko'chirilmagan. Yangi mashinada qaytadan yarating:

```bash
conda create -n musetalk python=3.10 -y
conda activate musetalk
pip install -r models/MuseTalk/requirements.txt
pip install -r backend/requirements.txt
```

MuseTalk model fayllari `models/MuseTalk/models/` ichida tayyor turibdi
(`musetalkV15`, `sd-vae`, `whisper`, `dwpose`, `face-parse-bisent`, ...).

## 5. Frontend'ni build qilish

Admin panel `/studio` ostida `frontend/dist` dan beriladi. Manba o'zgarsa
qaytadan build qiling:

```bash
cd frontend
npm install          # birinchi marta
npm run build        # → frontend/dist
```

Ishlab chiqish (hot-reload) rejimi — Vite dev server (port 5173), backend'ga
`/api`, `/chat-stream`, `/voices`, `/idle.jpg`, `/videos` so'rovlarini proksilaydi:

```bash
cd frontend
npm run dev          # http://localhost:5173
```

> Dev rejimda backend ham (port 8100) ishlab turishi shart.

## 6. Backend'ni ishga tushirish

```bash
cd Avatar_Studio/backend
bash run.sh
```

`run.sh` quyidagilarni avtomatik aniqlaydi:
- `BASE` = `backend/` papka
- `MT_DIR` = `../models/MuseTalk` (yoki `MT_DIR` env o'zgaruvchisi)
- `.env` dan kalitlarni yuklaydi
- `uvicorn app.main:app --host 0.0.0.0 --port 8100` ni ishga tushiradi

So'ng brauzerda oching: **http://localhost:8100/studio**

## 7. Tekshiruv

- `/studio` — admin panel (dashboard, editor, chat, analitika)
- `/api/avatars` — avatarlar ro'yxati (CRUD `data/avatars.json` ga saqlanadi)
- `/api/analytics` — real analitika (`data/events.jsonl` dan)
- `/health` — model holati, kalitlar, kesh statistikasi
- Chat — madina_lp uchun haqiqiy GPT+TTS+MuseTalk video chiqaradi

## 8. Yangi avatar haqida

Yangi yaratilgan avatarlar `real=false` bo'ladi: ular madina_lp yuzini ulashadi,
lekin o'z ovozi va personasini oladi. Har bir avatarga alohida **video** kerak bo'lsa,
MuseTalk preprocessing'ni o'sha avatar tasviri ustida offline ishga tushirish kerak.

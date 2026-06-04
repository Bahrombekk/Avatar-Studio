"""Real-time ovozli suhbat moduli (alohida) — mikrofon → STT → GPT → TTS → video.

Eski chat/avatar logikasiga tegmaydi: mavjud servislarni (pipeline, gpt, tts,
musetalk, avatar_store) faqat IMPORT qilib qayta ishlatadi. WebSocket orqali
ishlaydi: /api/realtime/ws.
"""

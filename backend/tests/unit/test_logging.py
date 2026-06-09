"""Strukturali logging — JSON maydonlar, ko'p-kontekstli ID (log_context), fayl handler."""
import io
import json
import logging
import logging.handlers

from app.core import logging as alog


def _capture(fmt=None):
    """JsonFormatter + _ContextFilter bilan izolyatsiyalangan logger + bufer qaytaradi."""
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.addFilter(alog._ContextFilter())
    h.setFormatter(fmt or alog.JsonFormatter())
    lg = logging.getLogger("test.super")
    lg.handlers.clear()
    lg.addHandler(h)
    lg.setLevel(logging.DEBUG)
    lg.propagate = False
    return lg, buf


def test_json_core_fields():
    lg, buf = _capture()
    lg.info("salom", extra={"foo": 1})
    rec = json.loads(buf.getvalue().strip())
    assert rec["msg"] == "salom"
    assert rec["level"] == "INFO"
    assert rec["request_id"] == "-"
    assert "pid" in rec
    assert rec["foo"] == 1
    # avatar_id/session_id o'rnatilmagan → JSON'da bo'lmaydi (shovqin kam)
    assert "avatar_id" not in rec and "session_id" not in rec


def test_log_context_injects_and_resets():
    lg, buf = _capture()
    with alog.log_context(avatar_id="madina_lp", session_id="s123"):
        lg.info("ichkarida")
    rec = json.loads(buf.getvalue().strip())
    assert rec["avatar_id"] == "madina_lp"
    assert rec["session_id"] == "s123"
    # blokdan keyin tiklanadi
    buf.truncate(0); buf.seek(0)
    lg.info("tashqarida")
    rec2 = json.loads(buf.getvalue().strip())
    assert "avatar_id" not in rec2


def test_log_context_nested():
    assert alog.avatar_id_ctx.get() == "-"
    with alog.log_context(avatar_id="a"):
        assert alog.avatar_id_ctx.get() == "a"
        with alog.log_context(avatar_id="b"):
            assert alog.avatar_id_ctx.get() == "b"
        assert alog.avatar_id_ctx.get() == "a"          # ichki blok tiklandi
    assert alog.avatar_id_ctx.get() == "-"              # tashqi ham tiklandi


def test_request_id_in_output():
    lg, buf = _capture()
    tok = alog.request_id_ctx.set("req99")
    try:
        lg.info("x")
    finally:
        alog.request_id_ctx.reset(tok)
    assert json.loads(buf.getvalue().strip())["request_id"] == "req99"


def test_exc_info_field():
    lg, buf = _capture()
    try:
        raise ValueError("boom")
    except ValueError:
        lg.error("xato", exc_info=True)
    rec = json.loads(buf.getvalue().strip())
    assert "exc" in rec and "ValueError" in rec["exc"]


def test_non_serializable_extra_does_not_crash():
    lg, buf = _capture()
    lg.info("obj", extra={"obj": object()})       # default=str → crash bo'lmaydi
    rec = json.loads(buf.getvalue().strip())
    assert "obj" in rec


def test_configure_logging_writes_rotating_file(tmp_path):
    logfile = tmp_path / "sub" / "app.log"          # papka avtomatik yaratilishini ham tekshiradi
    try:
        alog.configure_logging("INFO", "json", log_file=str(logfile), max_mb=1, backups=2)
        logging.getLogger("test.file").info("fayl logi", extra={"k": "v"})
        for h in logging.getLogger().handlers:
            h.flush()
        line = logfile.read_text(encoding="utf-8").strip().splitlines()[-1]
        rec = json.loads(line)
        assert rec["msg"] == "fayl logi" and rec["k"] == "v"
    finally:
        for h in list(logging.getLogger().handlers):
            if isinstance(h, logging.handlers.RotatingFileHandler):
                h.close()
        alog.configure_logging("INFO", "text")      # global holatni stdout-only ga qaytaramiz

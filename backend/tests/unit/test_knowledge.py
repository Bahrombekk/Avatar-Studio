"""RAG bilim bazasi — chunking, CRUD, cosine retrieval (embed mock bilan)."""
import numpy as np
import pytest

from app.services import knowledge


def test_chunk_text_basic():
    assert knowledge.chunk_text("") == []
    one = knowledge.chunk_text("Qisqa matn.")
    assert one == ["Qisqa matn."]
    # Ko'p paragraf → bir nechta chunk, har biri _CHUNK_MAX dan kichik.
    big = "\n\n".join(["Gap " * 40 for _ in range(6)])
    chunks = knowledge.chunk_text(big)
    assert len(chunks) >= 2
    assert all(len(c) <= knowledge._CHUNK_MAX for c in chunks)


def _fake_embed(monkeypatch, mapping):
    """knowledge._embed ni determinik vektorlarga monkeypatch qiladi."""
    def fake(texts):
        return [mapping(t) for t in texts]
    monkeypatch.setattr(knowledge, "_embed", fake)


def test_faq_add_list_delete_and_retrieve(monkeypatch):
    # Oddiy "embedding": kalit so'z bo'lsa [1,0], aks holda [0,1].
    def emb(t):
        return [1.0, 0.0] if "chipta" in t.lower() else [0.0, 1.0]
    _fake_embed(monkeypatch, emb)

    aid = "av_kn_test"
    res = knowledge.add_faq(aid, "Chipta narxi qancha?", "150 ming so'm")
    assert res["id"].startswith("faq_")
    lst = knowledge.list_knowledge(aid)
    assert len(lst["faqs"]) == 1

    # Mos savol → FAQ javobi qaytadi (kind=faq, answer matni).
    hits = knowledge.retrieve(aid, "chipta qancha turadi", k=3, min_score=0.5)
    assert hits and hits[0]["kind"] == "faq"
    assert "150 ming" in hits[0]["text"]

    # Mos kelmaydigan savol → past score, [].
    assert knowledge.retrieve(aid, "butunlay boshqa narsa", min_score=0.5) == []

    # O'chirish → bo'sh.
    fid = lst["faqs"][0]["id"]
    assert knowledge.delete_faq(aid, fid) is True
    assert knowledge.list_knowledge(aid)["faqs"] == []
    assert knowledge.retrieve(aid, "chipta qancha") == []


def test_file_source_chunks_and_delete(monkeypatch):
    _fake_embed(monkeypatch, lambda t: [float(len(t) % 5), 1.0])
    aid = "av_kn_doc"
    text = "\n\n".join(["Birinchi paragraf matni.", "Ikkinchi paragraf matni."])
    res = knowledge.add_file_source(aid, "doc.txt", text)
    assert res["n_chunks"] >= 1
    srcs = knowledge.list_knowledge(aid)["sources"]
    assert srcs and srcs[0]["name"] == "doc.txt"
    assert knowledge.delete_source(aid, srcs[0]["id"]) is True
    assert knowledge.list_knowledge(aid)["sources"] == []


def test_retrieve_empty_returns_list():
    # Hech narsa qo'shilmagan avatar → [] (degradatsiya, xato emas).
    assert knowledge.retrieve("av_yoq_kn", "savol") == []


def test_build_context_block():
    assert knowledge.build_context_block([]) == ""
    block = knowledge.build_context_block([{"text": "150 ming", "kind": "faq"}])
    assert "FAQ" in block and "150 ming" in block

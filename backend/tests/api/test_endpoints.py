"""API darajasi testlari — TestClient (og'ir ML import qilinmaydi)."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # Yengil muhitda model "loading"/"unavailable" (torch yo'q) — lekin javob 200.
    assert "model" in body and "cache" in body


def test_metrics(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    j = r.json()
    assert "requests_total" in j and "latency_ms" in j
    assert {"p50", "p95", "p99"} <= set(j["latency_ms"])


def test_voices(client):
    r = client.get("/voices")
    assert r.status_code == 200
    j = r.json()
    assert j["voices"] and "default" in j


def test_request_id_header(client):
    r = client.get("/health")
    assert r.headers.get("X-Request-ID")


def test_avatars_list_public(client):
    r = client.get("/api/avatars")
    assert r.status_code == 200
    assert "avatars" in r.json()


def test_avatar_404(client):
    assert client.get("/api/avatars/yshmas_id").status_code == 404


def test_admin_guarded_endpoints_require_auth(client):
    # Token'siz → 401
    assert client.get("/api/analytics").status_code == 401
    assert client.post("/cache/clear").status_code == 401
    assert client.post("/api/avatars", json={"name": "X"}).status_code == 401


def test_login_flow(client):
    bad = client.post("/api/auth/login", json={"password": "wrong"})
    assert bad.status_code == 401
    good = client.post("/api/auth/login", json={"password": "test-pw"})
    assert good.status_code == 200
    token = good.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/check", headers=headers).status_code == 200
    assert client.get("/api/analytics", headers=headers).status_code == 200


def test_admin_create_avatar_with_token(client, admin_headers):
    r = client.post("/api/avatars", json={"name": "CI Avatar"}, headers=admin_headers)
    assert r.status_code == 200
    aid = r.json()["id"]
    client.delete(f"/api/avatars/{aid}", headers=admin_headers)


def test_video_path_traversal_guard(client):
    # Studio render_id ichida '\' (kodlangan %5c) → traversal guard 404.
    assert client.get("/api/studio/render/a%5c..%5cb/video").status_code >= 400
    # Noto'g'ri kengaytma / mavjud bo'lmagan kesh videosi → 404.
    assert client.get("/videos/av_x/madina/yoq.txt").status_code >= 400
    assert client.get("/videos/av_x/madina/yoq.mp4").status_code == 404

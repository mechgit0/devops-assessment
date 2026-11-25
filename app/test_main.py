from app.main import app


def test_index_returns_greeting():
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Hello, DevOps" in resp.get_data(as_text=True)


def test_health_returns_ok():
    client = app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}

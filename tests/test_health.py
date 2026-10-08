def test_health_check_retorna_200(client):
    if not client:
        return
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_ready_check_retorna_200(client):
    if not client:
        return
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"

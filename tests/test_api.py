"""Pruebas funcionales de endpoints API del bot y entradas."""

from datetime import datetime
from app.models.entry import Entry, RunLog


def test_estado_bot_retorna_idle(client):
    """Comprueba que el estado inicial del bot sea inactivo."""
    response = client.get("/api/v1/bot/status")
    assert response.status_code == 200
    assert response.json()["status"] == "idle"


def test_estadisticas_iniciales_vacias(client):
    """Comprueba que las estadísticas iniciales devuelvan ceros sin errores."""
    response = client.get("/api/v1/entries/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_entradas"] == 0
    assert data["total_puntos_gastados"] == 0
    assert data["entradas_hoy"] == 0


def test_registro_y_consulta_de_entradas(client, db_session):
    """Verifica que una entrada guardada se liste y se compute en estadísticas."""
    run = RunLog(
        status="completed",
        total_entries=1,
        total_points_spent=40,
        initial_points=400,
        final_points=360,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    entry = Entry(
        game_name="Disco Elysium - The Final Cut",
        giveaway_code="AbC12",
        giveaway_url="https://www.steamgifts.com/giveaway/AbC12/disco-elysium",
        category="wishlist",
        points_spent=40,
        points_remaining=360,
        entries_count=2344,
        copies=1,
        result="success",
        time_remaining="3 hours remaining",
        run_id=run.id,
    )
    db_session.add(entry)
    db_session.commit()

    # Consultar listado de entradas
    response = client.get("/api/v1/entries/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["entries"][0]["game_name"] == "Disco Elysium - The Final Cut"
    assert data["entries"][0]["category"] == "wishlist"

    # Consultar estadísticas
    stats_resp = client.get("/api/v1/entries/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_entradas"] == 1
    assert stats["total_puntos_gastados"] == 40
    assert stats["por_categoria"]["wishlist"] == 1
    assert stats["juegos_top"][0]["juego"] == "Disco Elysium - The Final Cut"


def test_consulta_detalle_ejecucion(client, db_session):
    """Verifica la consulta de detalle de una ronda de ejecución."""
    run = RunLog(
        status="completed",
        total_entries=2,
        total_points_spent=60,
        initial_points=400,
        final_points=340,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    response = client.get(f"/api/v1/entries/runs/{run.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["run"]["id"] == run.id
    assert data["run"]["status"] == "completed"
    assert data["run"]["total_entries"] == 2


def test_obtener_y_actualizar_categorias_api(client):
    """Verifica que la API permita consultar y actualizar el orden de categorías."""
    response = client.get("/api/v1/bot/categories")
    assert response.status_code == 200
    data = response.json()
    assert "categories" in data
    assert len(data["categories"]) == 7

    # Actualizar orden vía API
    nuevo_orden = [
        "wishlist",
        "dlc",
        "group",
        "Multiple Copies",
        "recommended",
        "new",
        "all",
    ]
    post_resp = client.post(
        "/api/v1/bot/categories",
        json={"order": nuevo_orden, "enabled": nuevo_orden},
    )
    assert post_resp.status_code == 200
    assert post_resp.json()["success"] is True

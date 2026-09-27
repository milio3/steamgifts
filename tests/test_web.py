"""Pruebas funcionales de las vistas web y componentes parciales HTMX."""

from app.models.entry import Entry, RunLog


def test_vista_dashboard_retorna_200(client):
    """Comprueba que la vista principal del dashboard cargue correctamente."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Panel de Control" in response.text
    assert "Ejecutar Bot" in response.text


def test_vista_entries_retorna_200(client):
    """Comprueba que la vista de historial de entradas cargue correctamente."""
    response = client.get("/entries")
    assert response.status_code == 200
    assert "Historial de Entradas" in response.text


def test_vista_runs_retorna_200(client):
    """Comprueba que la vista de ejecuciones cargue correctamente."""
    response = client.get("/runs")
    assert response.status_code == 200
    assert "Registro de Ejecuciones" in response.text


def test_vista_config_retorna_200(client):
    """Comprueba que la vista de configuración cargue correctamente."""
    response = client.get("/config")
    assert response.status_code == 200
    assert "Configuración" in response.text
    assert "Diagnóstico de Conexión" in response.text


def test_parcial_stats_renderiza_metricas(client, db_session):
    """Comprueba que el componente de estadísticas renderice los datos de BD."""
    run = RunLog(status="completed", total_entries=3, total_points_spent=70)
    db_session.add(run)
    db_session.commit()

    response = client.get("/partials/stats")
    assert response.status_code == 200
    assert "Total Entradas" in response.text
    assert "Puntos Gastados" in response.text


def test_parcial_bot_status_inactivo(client):
    """Comprueba el badge parcial del estado del bot."""
    response = client.get("/partials/bot-status")
    assert response.status_code == 200
    assert "INACTIVO" in response.text


def test_parcial_tabla_entradas(client, db_session):
    """Comprueba que el componente parcial de tabla renderice entradas."""
    entry = Entry(
        game_name="Monster Boy and the Cursed Kingdom",
        giveaway_code="XyZ99",
        category="wishlist",
        points_spent=30,
        result="success",
    )
    db_session.add(entry)
    db_session.commit()

    response = client.get("/partials/entries-table")
    assert response.status_code == 200
    assert "Monster Boy and the Cursed Kingdom" in response.text
    assert "30P" in response.text
    assert "Éxito" in response.text

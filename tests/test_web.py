"""Pruebas funcionales de las vistas web y componentes parciales HTMX."""

from app.models.entry import Entry, RunLog


def test_vista_dashboard_retorna_200(client):
    """Comprueba que la vista principal del dashboard cargue correctamente."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Panel de Control" in response.text
    assert "Iniciar Ejecución" in response.text


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
    """Comprueba el badge parcial del estado del bot en reposo."""
    response = client.get("/partials/bot-status")
    assert response.status_code == 200
    assert "Sistema en espera" in response.text


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


def test_dashboard_consola_y_sesiones(client):
    """Verifica que el dashboard tenga la consola en vivo, tema oscuro y sesiones."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert 'data-bs-theme="dark"' in response.text
    assert "terminal-window" in response.text
    assert "console-body" in response.text
    assert "sessions-container" in response.text
    assert "btn-run-bot" in response.text


def test_parcial_consola_logs(client):
    """Verifica que el endpoint de consola devuelva logs formateados."""
    response = client.get("/partials/console-logs")
    assert response.status_code == 200
    assert "console-line" in response.text or "steamgifts-bot" in response.text


def test_parcial_sesiones_ejecucion(client, db_session):
    """Verifica que el endpoint de sesiones devuelva las ejecuciones con sus entradas."""
    run = RunLog(
        status="completed",
        total_entries=1,
        total_points_spent=50,
        initial_points=400,
        final_points=350,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    entry = Entry(
        game_name="Cyberpunk 2077",
        giveaway_code="Cp77X",
        giveaway_url="https://www.steamgifts.com/giveaway/Cp77X/cyberpunk-2077",
        category="wishlist",
        points_spent=50,
        points_remaining=350,
        result="success",
        run_id=run.id,
    )
    db_session.add(entry)
    db_session.commit()

    response = client.get("/partials/execution-sessions")
    assert response.status_code == 200
    assert f"#{run.id}" in response.text
    assert "Cyberpunk 2077" in response.text
    assert "50P" in response.text


def test_configuracion_editable_y_guardado(client, monkeypatch):
    """Verifica que la vista de configuración sea editable y guarde parámetros y orden."""
    monkeypatch.setattr("app.web.routes.update_settings_and_env", lambda updates: True)
    resp_cfg = client.get("/config")
    assert resp_cfg.status_code == 200
    assert 'name="phpsessid"' in resp_cfg.text
    assert 'name="max_entries_per_run"' in resp_cfg.text
    assert "category-sortable-item" in resp_cfg.text

    nuevo_orden = {
        "phpsessid": "cookie_test_12345",
        "max_entries_per_run": "30",
        "http_timeout_seconds": "18.0",
        "min_delay_seconds": "4.0",
        "max_delay_seconds": "9.0",
        "category_delay_seconds": "6.0",
        "category_order": ["all", "wishlist", "recommended", "multiple_copies", "dlc", "group", "new"],
    }
    response = client.post("/partials/save-config", data=nuevo_orden)
    assert response.status_code == 200
    assert "guardada" in response.text.lower()

    # Comprobar que en config 'all' ahora aparece primero
    resp_cfg2 = client.get("/config")
    assert resp_cfg2.status_code == 200
    idx_all = resp_cfg2.text.find('data-category="all"')
    idx_wishlist = resp_cfg2.text.find('data-category="wishlist"')
    assert idx_all != -1 and idx_wishlist != -1
    assert idx_all < idx_wishlist


def test_parcial_account_points(client, monkeypatch):
    """Comprueba el endpoint de consulta de puntos disponibles."""
    from app.schemas.giveaway import AccountInfo
    monkeypatch.setattr(
        "app.services.steamgifts_client.SteamGiftsClient.is_session_valid",
        lambda self: True,
    )
    monkeypatch.setattr(
        "app.services.steamgifts_client.SteamGiftsClient.get_account_info",
        lambda self: AccountInfo(points=385, level=4, username="testuser", xsrf_token="tok"),
    )
    from app.core.config import settings
    monkeypatch.setattr(settings, "STEAMGIFTS_PHPSESSID", "dummy_sess")

    response = client.get("/partials/account-points")
    assert response.status_code == 200
    assert "385p" in response.text
    assert "testuser" in response.text


def test_parcial_test_telegram(client, monkeypatch):
    """Comprueba el endpoint de prueba de Telegram."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "TELEGRAM_ALERTS_ENABLED", True)
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "dummy_token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "dummy_chat")
    monkeypatch.setattr(
        "app.services.telegram_alert.send_telegram_message",
        lambda text: True,
    )
    response = client.post("/partials/test-telegram")
    assert response.status_code == 200
    assert "Mensaje enviado" in response.text


def test_parcial_config_modal(client):
    """Comprueba que el endpoint parcial para el modal de configuración funcione."""
    response = client.get("/partials/config-modal")
    assert response.status_code == 200
    assert "config-form" in response.text
    assert "Diagnóstico de Conexión" in response.text
    assert "category-sortable-item" in response.text


def test_favicon_retorna_200(client):
    """Comprueba que el favicon se sirva correctamente."""
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert "svg" in response.headers.get("content-type", "")


def test_diferenciacion_ejecucion_manual_y_automatica(client, db_session):
    """Verifica que las ejecuciones manuales y automáticas muestren sus respectivos badges."""
    run_manual = RunLog(
        status="completed",
        total_entries=2,
        total_points_spent=60,
        trigger_type="manual",
    )
    run_auto = RunLog(
        status="completed",
        total_entries=3,
        total_points_spent=90,
        trigger_type="auto",
    )
    db_session.add_all([run_manual, run_auto])
    db_session.commit()

    # Probar en sesiones del dashboard
    resp_sessions = client.get("/partials/execution-sessions")
    assert resp_sessions.status_code == 200
    assert "badge-trigger-manual" in resp_sessions.text
    assert "badge-trigger-auto" in resp_sessions.text

    # Probar en tabla de ejecuciones
    resp_runs = client.get("/partials/runs-table")
    assert resp_runs.status_code == 200
    assert "badge-trigger-manual" in resp_runs.text
    assert "badge-trigger-auto" in resp_runs.text

    # Probar en modal de detalle de auto
    resp_modal = client.get(f"/partials/runs/{run_auto.id}/modal")
    assert resp_modal.status_code == 200
    assert "Automática" in resp_modal.text
    assert "badge-trigger-auto" in resp_modal.text


def test_pie_de_pagina_muestra_version(client):
    """Comprueba que el pie de página incluya la versión dinámica de la aplicación."""
    from app.core.config import settings

    response = client.get("/dashboard")
    assert response.status_code == 200
    assert f"v{settings.VERSION}" in response.text
    assert "SteamGifts Auto-Enter Bot" in response.text





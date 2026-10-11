"""Pruebas unitarias para la detección de juegos ganados y visualización del banner en el Dashboard."""

from unittest.mock import MagicMock, patch
from app.schemas.giveaway import AccountInfo
from app.services.steamgifts_client import SteamGiftsClient


HTML_MAIN_PAGE_WITH_NOTIFICATION = """
<html>
<head><title>SteamGifts</title></head>
<body>
    <input type="hidden" name="xsrf_token" value="abc123token" />
    <span class="nav__points">350</span>
    <span title="3.5">Level 3</span>
    <a class="nav__avatar-outer-wrap" href="/user/GamerPro"></a>
    <a class="nav__button" href="/giveaways/won" title="Giveaways Won">
        <i class="fa fa-trophy"></i>
        <div class="nav__notification">2</div>
    </a>
</body>
</html>
"""


def test_get_account_info_extracts_won_pending():
    """Valida que get_account_info detecte el número de juegos ganados pendientes en la navbar de SteamGifts."""
    client = SteamGiftsClient("dummy", "https://www.steamgifts.com", "dummy_ua", 5.0)
    mock_response = MagicMock()
    mock_response.text = HTML_MAIN_PAGE_WITH_NOTIFICATION
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch.object(client.session, "get", return_value=mock_response):
        info = client.get_account_info(force=True)
        assert info.username == "GamerPro"
        assert info.points == 350
        assert info.won_pending == 2


def test_dashboard_shows_won_banner_when_won_pending(client):
    """Valida que el Dashboard muestre el banner destacado cuando hay juegos ganados pendientes."""
    mock_account = AccountInfo(
        points=250,
        level=2,
        username="WinnerUser",
        xsrf_token="token123",
        won_pending=1,
    )

    with patch("app.services.steamgifts_client.SteamGiftsClient.get_account_info", return_value=mock_account):
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "alert-won-banner" in response.text
        assert "Has ganado 1 sorteo(s) en SteamGifts!" in response.text
        assert "https://www.steamgifts.com/giveaways/won" in response.text


def test_dashboard_hides_won_banner_when_no_won(client):
    """Valida que el Dashboard NO muestre el banner si no hay juegos ganados pendientes."""
    from app.services.points_checker import points_checker
    points_checker._last_won_pending = 0

    mock_account = AccountInfo(
        points=250,
        level=2,
        username="RegularUser",
        xsrf_token="token123",
        won_pending=0,
    )

    with patch("app.services.steamgifts_client.SteamGiftsClient.get_account_info", return_value=mock_account):
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "alert-won-banner" not in response.text


def test_points_checker_detects_won_pending_and_logs(caplog):
    """Valida que PointsChecker detecte juegos ganados en cada chequeo y emita el aviso en el log/consola."""
    import logging
    from app.services.points_checker import PointsChecker

    checker = PointsChecker()
    mock_account = AccountInfo(
        points=120,
        level=2,
        username="LuckyWinner",
        xsrf_token="token123",
        won_pending=1,
    )

    with patch("app.core.config.settings.STEAMGIFTS_PHPSESSID", "dummy_sessid"), \
         patch("app.services.steamgifts_client.SteamGiftsClient.is_session_valid", return_value=True), \
         patch("app.services.steamgifts_client.SteamGiftsClient.get_account_info", return_value=mock_account), \
         caplog.at_level(logging.INFO):
        checker._check_points()

        assert checker._last_won_pending == 1
        assert checker.get_status()["won_pending"] == 1
        assert "Chequeo #1: 120 P (usuario: LuckyWinner) | Próximo chequeo" in caplog.text
        assert "🏆 [PREMIO] Tienes pendiente canjear un juego en SteamGifts" in caplog.text


def test_points_checker_detects_multiple_won_pending_and_logs(caplog):
    """Valida que PointsChecker gestione el mensaje en plural cuando hay múltiples premios pendientes."""
    import logging
    from app.services.points_checker import PointsChecker

    checker = PointsChecker()
    mock_account = AccountInfo(
        points=120,
        level=2,
        username="LuckyWinner",
        xsrf_token="token123",
        won_pending=3,
    )

    with patch("app.core.config.settings.STEAMGIFTS_PHPSESSID", "dummy_sessid"), \
         patch("app.services.steamgifts_client.SteamGiftsClient.is_session_valid", return_value=True), \
         patch("app.services.steamgifts_client.SteamGiftsClient.get_account_info", return_value=mock_account), \
         caplog.at_level(logging.INFO):
        checker._check_points()

        assert checker._last_won_pending == 3
        assert checker.get_status()["won_pending"] == 3
        assert "🏆 [PREMIO] Tienes pendientes canjear 3 juegos en SteamGifts" in caplog.text


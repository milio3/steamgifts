"""Pruebas unitarias y de integración para la detección y visualización de juegos ganados."""

from unittest.mock import MagicMock, patch
from app.schemas.giveaway import WonGiveawayInfo, AccountInfo
from app.services.steamgifts_client import SteamGiftsClient
from app.services.telegram_alert import notify_game_won


HTML_WON_ROW_SAMPLE = """
<div class="table__row-inner-wrap">
    <div>
        <a class="table_image_thumbnail" href="/giveaway/wpuIn/100-hidden-snails" style="background-image:url(https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1446330/capsule_184x69.jpg?t=1710886158);"></a>
    </div>
    <div class="table__column--width-fill">
        <p><a class="table__column__heading" href="/giveaway/wpuIn/100-hidden-snails">100 hidden snails</a></p>
        <p>Ended <span data-timestamp="1791413940">17 hours</span> ago</p>
    </div>
    <div class="table__column--width-medium text-center">
        <div class="view_key_btn" data-form="do=view_key&winner_id=10353245&xsrf_token=ff9a1b07700e435744ab69020fcc5c9d">
            <div class="show_key_default"><i class="fa fa-fw fa-key"></i><span>View Key</span></div>
        </div>
    </div>
    <div class="table__column--width-small text-center table__column--gift-feedback">
        <div class="table__gift-feedback-awaiting-reply" data-feedback="1">
            <i class="fa fa-circle-o"></i> Received
        </div>
        <div class="table__gift-feedback-received is-hidden" data-feedback="">
            <i class="icon-green fa fa-check-circle"></i> Received
        </div>
    </div>
</div>
"""

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


def test_parsing_won_giveaway_row():
    """Valida el parseo correcto de una fila HTML de sorteos ganados."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(HTML_WON_ROW_SAMPLE, "html.parser")
    row = soup.select_one(".table__row-inner-wrap")

    client = SteamGiftsClient("dummy", "https://www.steamgifts.com", "dummy_ua", 5.0)
    item = client._parse_won_giveaway_row(row)

    assert item is not None
    assert item.game_name == "100 hidden snails"
    assert item.giveaway_code == "wpuIn"
    assert "https://www.steamgifts.com/giveaway/wpuIn/100-hidden-snails" in item.giveaway_url
    assert "1446330" in item.steam_image_url
    assert item.ended_timestamp == 1791413940
    assert item.ended_text == "17 hours"
    assert item.feedback_status == "pending_feedback"
    assert item.has_key is True


def test_get_account_info_extracts_won_pending():
    """Valida que get_account_info detecte el número de juegos ganados pendientes en la navbar."""
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


def test_api_won_giveaways(client):
    """Valida el endpoint de la API REST /api/v1/bot/won."""
    mock_won_items = [
        WonGiveawayInfo(
            game_name="Half-Life 3",
            giveaway_code="HL3CODE",
            giveaway_url="https://www.steamgifts.com/giveaway/HL3CODE/",
            steam_image_url="https://steamstatic.com/app/123.jpg",
            ended_timestamp=1700000000,
            ended_text="2 days",
            feedback_status="pending_feedback",
            has_key=True,
        )
    ]

    with patch("app.services.steamgifts_client.SteamGiftsClient.get_won_giveaways", return_value=mock_won_items):
        response = client.get("/api/v1/bot/won")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["game_name"] == "Half-Life 3"
        assert data[0]["giveaway_code"] == "HL3CODE"
        assert data[0]["feedback_status"] == "pending_feedback"


def test_web_won_page_and_partial(client):
    """Valida la carga de la vista HTML /won y el parcial /partials/won-table."""
    mock_account = AccountInfo(
        points=250,
        level=2,
        username="TestWinner",
        xsrf_token="token123",
        won_pending=1,
    )
    mock_won_items = [
        WonGiveawayInfo(
            game_name="Portal 2",
            giveaway_code="PORTAL2",
            giveaway_url="https://www.steamgifts.com/giveaway/PORTAL2/",
            steam_image_url="https://steamstatic.com/app/620.jpg",
            ended_timestamp=1700000000,
            ended_text="1 day",
            feedback_status="pending_feedback",
            has_key=True,
        )
    ]

    with patch("app.services.steamgifts_client.SteamGiftsClient.get_account_info", return_value=mock_account), \
         patch("app.services.steamgifts_client.SteamGiftsClient.get_won_giveaways", return_value=mock_won_items):
        # Vista principal /won
        resp_view = client.get("/won")
        assert resp_view.status_code == 200
        assert "Juegos Ganados" in resp_view.text

        # Parcial de tabla /partials/won-table
        resp_table = client.get("/partials/won-table")
        assert resp_table.status_code == 200
        assert "Portal 2" in resp_table.text
        assert "PORTAL2" in resp_table.text
        assert "Pendiente Confirmar" in resp_table.text


def test_telegram_notify_game_won():
    """Valida el envío de notificación de juego ganado por Telegram."""
    with patch("app.services.telegram_alert.send_telegram_message", return_value=True) as mock_send:
        exito = notify_game_won("Cyberpunk 2077", "https://www.steamgifts.com/giveaway/XYZ/", count=1)
        assert exito is True
        mock_send.assert_called_once()
        assert "Cyberpunk 2077" in mock_send.call_args[0][0]

"""Servicio de alertas vía Telegram Bot para notificación de puntos y eventos."""

import html
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

# Control en memoria para no repetir la alerta de límite continuamente (cooldown de 2 horas)
_LAST_ALERT_SENT_AT: Optional[datetime] = None
_ALERT_COOLDOWN_HOURS: int = 2


def send_telegram_message(text: str) -> bool:
    """Envía un mensaje de texto formateado en HTML al chat de Telegram configurado."""
    if not settings.TELEGRAM_ALERTS_ENABLED:
        logger.debug("Alertas de Telegram desactivadas en la configuración.")
        return False

    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.warning("No se ha configurado TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID.")
        return False

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=settings.HTTP_TIMEOUT_SECONDS)
        if response.status_code == 200:
            logger.info("Notificación enviada a Telegram con éxito.")
            return True
        else:
            logger.error(
                "Fallo al enviar notificación a Telegram: HTTP %s - %s",
                response.status_code,
                response.text,
            )
            return False
    except Exception as e:
        logger.error("Error de conexión al enviar alerta a Telegram: %s", e)
        return False


def notify_points_threshold_exceeded(points: int, username: str = "Usuario", force: bool = False) -> bool:
    """Verifica si se ha alcanzado el límite de puntos y envía una alerta a Telegram respetando el cooldown."""
    global _LAST_ALERT_SENT_AT

    threshold = settings.TELEGRAM_POINTS_THRESHOLD
    if points < threshold:
        return False

    now = datetime.now()
    if not force and _LAST_ALERT_SENT_AT is not None:
        if now - _LAST_ALERT_SENT_AT < timedelta(hours=_ALERT_COOLDOWN_HOURS):
            logger.info(
                "Alerta de puntos (%s P) omitida por cooldown (último aviso hace menos de %sh).",
                points,
                _ALERT_COOLDOWN_HOURS,
            )
            return False

    mensaje = (
        "⚠️ <b>SteamGifts Bot — Límite de Puntos Alcanzado</b>\n\n"
        f"Hola <b>{html.escape(username)}</b>, tu cuenta ha alcanzado o superado el umbral establecido:\n"
        f"💰 <b>Puntos actuales:</b> <code>{points} P</code> (Límite: {threshold} P)\n\n"
        "<i>Te recomendamos iniciar una ronda de ejecución del bot para gastar puntos y no desperdiciar la regeneración automática de SteamGifts.</i>"
    )

    enviado = send_telegram_message(mensaje)
    if enviado:
        _LAST_ALERT_SENT_AT = now
    return enviado


def notify_automatic_run_completed(run_id: int, entries: int, points_spent: int, points_remaining: int) -> bool:
    """Envía un resumen a Telegram tras completarse una ejecución automática."""
    mensaje = (
        "✅ <b>SteamGifts Bot — Ejecución Automática Finalizada</b>\n\n"
        f"Ronda <b>#{run_id}</b> completada con éxito:\n"
        f"🎁 <b>Entradas realizadas:</b> {entries}\n"
        f"💸 <b>Puntos gastados:</b> {points_spent} P\n"
        f"💰 <b>Puntos restantes:</b> {points_remaining} P"
    )
    return send_telegram_message(mensaje)


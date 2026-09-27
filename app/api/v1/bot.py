"""Endpoints API para controlar el bot: ejecutar, estado y cuenta."""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

import app.main as main_app
from app.core.config import settings
from app.core.database import SessionLocal
from app.schemas.giveaway import AccountInfo, RunRequest
from app.services.bot_engine import BotEngine
from app.services.steamgifts_client import SteamGiftsClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bot", tags=["Bot"])


def _crear_cliente() -> SteamGiftsClient:
    """Crea una instancia del cliente SteamGifts con la configuración actual."""
    if not settings.STEAMGIFTS_PHPSESSID:
        raise HTTPException(
            status_code=400,
            detail="Cookie PHPSESSID no configurada. Edita el fichero .env",
        )
    return SteamGiftsClient(
        phpsessid=settings.STEAMGIFTS_PHPSESSID,
        base_url=settings.STEAMGIFTS_BASE_URL,
        user_agent=settings.USER_AGENT,
        timeout=settings.HTTP_TIMEOUT_SECONDS,
    )


def _ejecutar_bot_en_segundo_plano(categories: Optional[list] = None):
    """Función que ejecuta el bot en un hilo de background con su propia sesión de BD."""
    db = SessionLocal()
    try:
        main_app.is_bot_running = True
        client = _crear_cliente()
        engine = BotEngine(client, db)
        engine.run(categories=categories)
    except Exception as e:
        logger.error(f"Error en ejecución en segundo plano: {e}")
    finally:
        main_app.is_bot_running = False
        db.close()


@router.post("/run")
def ejecutar_bot(request: RunRequest, background_tasks: BackgroundTasks):
    """Inicia una ejecución del bot en segundo plano."""
    if getattr(main_app, "is_bot_running", False):
        return {
            "status": "error",
            "message": "El bot ya está ejecutándose. Espera a que termine.",
        }

    if not settings.STEAMGIFTS_PHPSESSID:
        return {
            "status": "error",
            "message": "Cookie PHPSESSID no configurada. Edita el fichero .env",
        }

    background_tasks.add_task(_ejecutar_bot_en_segundo_plano, request.categories)
    return {
        "status": "started",
        "message": "Ejecución iniciada en segundo plano",
        "categories": request.categories or list(BotEngine.CATEGORY_PRIORITY.keys()),
    }


@router.get("/status")
def estado_bot():
    """Devuelve el estado actual del bot (running/idle)."""
    running = getattr(main_app, "is_bot_running", False)
    return {"status": "running" if running else "idle"}


@router.get("/account", response_model=AccountInfo)
def informacion_cuenta():
    """Obtiene la información actual de la cuenta en SteamGifts."""
    client = _crear_cliente()
    return client.get_account_info()

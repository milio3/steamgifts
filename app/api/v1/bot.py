"""Endpoints API para controlar el bot: ejecutar, estado y cuenta."""

import logging
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

import app.main as main_app
from app.core.categories import (
    AVAILABLE_CATEGORIES,
    load_categories_config,
    save_categories_config,
)
from app.core.config import settings
from app.core.database import SessionLocal
from app.schemas.giveaway import (
    AccountInfo,
    CategoriesConfigRequest,
    RunRequest,
    WonGiveawayInfo,
)
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


def _ejecutar_bot_en_segundo_plano(categories: Optional[list] = None, trigger_type: str = "manual"):
    """Función que ejecuta el bot en un hilo de background con su propia sesión de BD."""
    from app.core.logging_buffer import console_handler

    # Limpiar la consola al inicio de cada ejecución para no mezclar logs anteriores
    console_handler.clear()

    db = SessionLocal()
    try:
        main_app.is_bot_running = True
        client = _crear_cliente()
        engine = BotEngine(client, db)
        summary = engine.run(categories=categories, trigger_type=trigger_type)
        if trigger_type == "auto":
            try:
                from app.services.telegram_alert import notify_automatic_run_completed
                notify_automatic_run_completed(
                    run_id=summary.run_id,
                    entries=summary.total_entries,
                    points_spent=summary.total_points_spent,
                    points_remaining=summary.final_points if summary.final_points is not None else 0,
                )
            except Exception as ex:
                logger.warning(f"No se pudo enviar resumen a Telegram: {ex}")
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

    order, enabled = load_categories_config()
    default_cats = [c for c in order if c in enabled and c in BotEngine.CATEGORY_PRIORITY]

    background_tasks.add_task(_ejecutar_bot_en_segundo_plano, request.categories)
    return {
        "status": "started",
        "message": "Ejecución iniciada en segundo plano",
        "categories": request.categories or default_cats,
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


@router.get("/won", response_model=List[WonGiveawayInfo])
def obtener_juegos_ganados(page: int = 1):
    """Obtiene el historial de sorteos ganados por el usuario."""
    client = _crear_cliente()
    return client.get_won_giveaways(page=page)


@router.get("/categories")
def obtener_categorias():
    """Devuelve la lista de categorías con su orden actual y estado de activación."""
    order, enabled = load_categories_config()
    resultado = []
    for idx, cat_id in enumerate(order, start=1):
        info = AVAILABLE_CATEGORIES.get(cat_id, {})
        resultado.append({
            "id": cat_id,
            "name": info.get("name", cat_id),
            "label": info.get("label", cat_id),
            "priority": idx,
            "enabled": cat_id in enabled,
            "url": info.get("url", ""),
        })
    return {"categories": resultado}


@router.post("/categories")
def actualizar_categorias(payload: CategoriesConfigRequest):
    """Actualiza el orden y activación de las categorías."""
    enabled_list = payload.enabled if payload.enabled is not None else payload.order
    ok = save_categories_config(payload.order, enabled_list)
    return {"success": ok, "categories_order": payload.order, "enabled_categories": enabled_list}

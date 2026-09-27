"""Rutas web del frontend: vistas HTML y endpoints parciales renderizados con Jinja2 y HTMX."""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

import app.main as main_app
from app.api.v1.bot import _ejecutar_bot_en_segundo_plano
from app.core.categories import (
    AVAILABLE_CATEGORIES,
    load_categories_config,
    save_categories_config,
)
from app.core.config import settings, update_settings_and_env
from app.core.database import get_db
from app.core.logging_buffer import console_handler
from app.models.entry import Entry, RunLog
from app.services.steamgifts_client import SteamGiftsClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Web"])

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)


# ─── Vistas principales ──────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def raiz():
    """Redirige la raíz al panel de control."""
    return RedirectResponse(url="/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Vista principal: panel de control con métricas, consola en vivo y sesiones."""
    order, _ = load_categories_config()
    configured_categories = []
    for idx, cat_id in enumerate(order, start=1):
        info = AVAILABLE_CATEGORIES.get(cat_id, {})
        configured_categories.append({
            "id": cat_id,
            "name": info.get("name", cat_id),
            "label": f"{idx}. {info.get('label', cat_id)}",
            "simple_label": f"{idx}. {info.get('name', cat_id)}",
            "badge_class": info.get("badge_class", f"badge-{cat_id}"),
            "priority": idx,
        })

    is_running = getattr(main_app, "is_bot_running", False)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "title": "Dashboard",
            "categories": configured_categories,
            "is_running": is_running,
        },
    )


@router.get("/entries", response_class=HTMLResponse)
async def historial(request: Request):
    """Vista del historial de entradas con filtros."""
    return templates.TemplateResponse(
        request=request, name="entries.html", context={"title": "Historial de Entradas"}
    )


@router.get("/runs", response_class=HTMLResponse)
async def ejecuciones(request: Request):
    """Vista de ejecuciones pasadas del bot."""
    return templates.TemplateResponse(
        request=request, name="runs.html", context={"title": "Ejecuciones"}
    )


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def detalle_ejecucion(request: Request, run_id: int):
    """Vista detallada de una ejecución específica."""
    return templates.TemplateResponse(
        request=request,
        name="run_detail.html",
        context={"title": f"Ejecución #{run_id}", "run_id": run_id},
    )


@router.get("/config", response_class=HTMLResponse)
async def configuracion(request: Request):
    """Vista de configuración editable directamente desde la app."""
    order, _ = load_categories_config()
    categories_list = []
    for idx, cat_id in enumerate(order, start=1):
        info = AVAILABLE_CATEGORIES.get(cat_id, {})
        categories_list.append({
            "id": cat_id,
            "name": info.get("name", cat_id),
            "label": f"{idx}. {info.get('label', cat_id)}",
            "raw_label": info.get("label", cat_id),
            "badge_class": info.get("badge_class", f"badge-{cat_id}"),
            "svg_icon": info.get("svg_icon", ""),
            "priority": idx,
        })

    cookie = settings.STEAMGIFTS_PHPSESSID
    cookie_oculta = ""
    if cookie:
        visible = min(8, len(cookie))
        cookie_oculta = cookie[:visible] + "•" * max(0, len(cookie) - visible)

    return templates.TemplateResponse(
        request=request,
        name="config.html",
        context={
            "title": "Configuración",
            "settings": settings,
            "cookie_oculta": cookie_oculta,
            "categories": categories_list,
        },
    )


# ─── Endpoints parciales HTMX ────────────────────────────────────────

@router.get("/partials/stats", response_class=HTMLResponse)
async def partial_stats(request: Request, db: Session = Depends(get_db)):
    """Fragmento HTML con las tarjetas de métricas del dashboard."""
    total_entradas = db.query(Entry).filter(Entry.result == "success").count()
    total_puntos = (
        db.query(func.sum(Entry.points_spent))
        .filter(Entry.result == "success")
        .scalar()
        or 0
    )
    hoy = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    entradas_hoy = (
        db.query(Entry)
        .filter(Entry.result == "success", Entry.timestamp >= hoy)
        .count()
    )
    ultima_run = db.query(RunLog).order_by(RunLog.started_at.desc()).first()

    return templates.TemplateResponse(
        request=request,
        name="components/stats_cards.html",
        context={
            "total_entradas": total_entradas,
            "total_puntos": total_puntos,
            "entradas_hoy": entradas_hoy,
            "ultima_run": ultima_run,
        },
    )


@router.get("/partials/execution-sessions", response_class=HTMLResponse)
async def partial_execution_sessions(request: Request, db: Session = Depends(get_db)):
    """Fragmento HTML con las sesiones de ejecución y todas sus entradas."""
    runs = (
        db.query(RunLog)
        .options(joinedload(RunLog.entries))
        .order_by(RunLog.started_at.desc())
        .limit(20)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="components/execution_sessions.html",
        context={"runs": runs},
    )


@router.get("/partials/console-logs", response_class=HTMLResponse)
async def partial_console_logs():
    """Fragmento HTML con los logs de la consola en tiempo real."""
    html_logs = console_handler.get_formatted_html()
    is_running = getattr(main_app, "is_bot_running", False)
    if is_running:
        html_logs += '\n<div class="console-line text-warning"><span class="spinner-border spinner-border-sm me-1"></span> Ejecutando bot en segundo plano... <span class="blink">▌</span></div>'
    return HTMLResponse(html_logs)


@router.post("/partials/clear-console", response_class=HTMLResponse)
async def partial_clear_console():
    """Limpia el buffer de la consola web."""
    console_handler.clear()
    return HTMLResponse('<div class="console-line text-muted fst-italic">consola@steamgifts-bot:~$ Consola limpiada.</div>')


@router.post("/partials/save-config", response_class=HTMLResponse)
async def partial_save_config(request: Request):
    """Guarda la configuración general y el orden de categorías desde la app."""
    form_data = await request.form()

    phpsessid = str(form_data.get("phpsessid", "")).strip()
    max_entries = str(form_data.get("max_entries_per_run", "25")).strip()
    timeout = str(form_data.get("http_timeout_seconds", "15.0")).strip()
    min_delay = str(form_data.get("min_delay_seconds", "3.0")).strip()
    max_delay = str(form_data.get("max_delay_seconds", "8.0")).strip()
    category_delay = str(form_data.get("category_delay_seconds", "5.0")).strip()

    updates = {}
    if phpsessid:
        updates["STEAMGIFTS_PHPSESSID"] = phpsessid
    if max_entries.isdigit():
        updates["MAX_ENTRIES_PER_RUN"] = int(max_entries)
    try:
        updates["HTTP_TIMEOUT_SECONDS"] = float(timeout)
        updates["MIN_DELAY_SECONDS"] = float(min_delay)
        updates["MAX_DELAY_SECONDS"] = float(max_delay)
        updates["CATEGORY_DELAY_SECONDS"] = float(category_delay)
    except ValueError:
        pass

    # Parámetros de Telegram
    telegram_enabled = "telegram_alerts_enabled" in form_data
    updates["TELEGRAM_ALERTS_ENABLED"] = telegram_enabled

    telegram_token = str(form_data.get("telegram_bot_token", "")).strip()
    if telegram_token:
        updates["TELEGRAM_BOT_TOKEN"] = telegram_token

    telegram_chat = str(form_data.get("telegram_chat_id", "")).strip()
    if telegram_chat:
        updates["TELEGRAM_CHAT_ID"] = telegram_chat

    telegram_threshold = str(form_data.get("telegram_points_threshold", "400")).strip()
    if telegram_threshold.isdigit():
        updates["TELEGRAM_POINTS_THRESHOLD"] = int(telegram_threshold)

    update_settings_and_env(updates)

    # Guardar orden de categorías
    categories_order = form_data.getlist("category_order")
    if categories_order:
        save_categories_config(categories_order, categories_order)

    return HTMLResponse(
        "<div class='alert alert-success d-flex align-items-center py-2 mb-0 shadow-sm animate-fade'>"
        "<i class='bi bi-check-circle-fill me-2 fs-5'></i>"
        "<div><strong>¡Configuración guardada!</strong> Los parámetros, alertas de Telegram y el orden de categorías han sido actualizados con éxito.</div>"
        "</div>"
    )


@router.get("/partials/entries-table", response_class=HTMLResponse)
async def partial_tabla_entradas(
    request: Request,
    category: Optional[str] = None,
    status: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    run_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Fragmento HTML con tabla filtrable y paginada de entradas."""
    query = db.query(Entry)

    if category:
        query = query.filter(Entry.category == category)
    if status:
        query = query.filter(Entry.result == status)
    if run_id:
        query = query.filter(Entry.run_id == run_id)
    if date_start:
        try:
            d_start = datetime.strptime(date_start, "%Y-%m-%d")
            query = query.filter(Entry.timestamp >= d_start)
        except ValueError:
            pass
    if date_end:
        try:
            d_end = datetime.strptime(date_end, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            query = query.filter(Entry.timestamp <= d_end)
        except ValueError:
            pass

    entries = (
        query.order_by(Entry.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="components/entries_table.html",
        context={"entries": entries},
    )


@router.get("/partials/runs-table", response_class=HTMLResponse)
async def partial_tabla_ejecuciones(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Fragmento HTML con la lista de ejecuciones del bot."""
    runs = (
        db.query(RunLog)
        .order_by(RunLog.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="components/runs_table.html",
        context={"runs": runs},
    )


@router.get("/partials/runs/{run_id}/summary", response_class=HTMLResponse)
async def partial_resumen_ejecucion(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db),
):
    """Fragmento HTML con la tarjeta de resumen de una ejecución."""
    run = db.query(RunLog).filter(RunLog.id == run_id).first()
    if not run:
        return HTMLResponse(
            "<div class='alert alert-warning'>Ejecución no encontrada.</div>"
        )
    return templates.TemplateResponse(
        request=request,
        name="components/run_summary.html",
        context={"run": run},
    )


@router.get("/partials/bot-status", response_class=HTMLResponse)
async def partial_estado_bot(request: Request):
    """Fragmento HTML con el indicador de estado del bot en la barra superior."""
    running = getattr(main_app, "is_bot_running", False)
    return templates.TemplateResponse(
        request=request,
        name="components/bot_status.html",
        context={"running": running},
    )


@router.post("/partials/run-bot", response_class=HTMLResponse)
async def partial_ejecutar_bot_formulario(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Lanza la ejecución del bot en segundo plano con las categorías configuradas."""
    if getattr(main_app, "is_bot_running", False):
        return HTMLResponse(
            "<div class='alert alert-warning py-2 mb-0 small'><i class='bi bi-exclamation-triangle'></i> El bot ya está en ejecución.</div>"
        )

    if not settings.STEAMGIFTS_PHPSESSID:
        return HTMLResponse(
            "<div class='alert alert-danger py-2 mb-0 small'><i class='bi bi-x-circle'></i> Cookie PHPSESSID no configurada. Ve a <a href='/config' class='alert-link'>Configuración</a> para ingresarla.</div>"
        )

    order, _ = load_categories_config()
    background_tasks.add_task(_ejecutar_bot_en_segundo_plano, order)
    return HTMLResponse(
        "<div class='alert alert-success py-2 mb-0 small animate-fade'>"
        "<i class='bi bi-check-circle me-1'></i> ¡Ejecución iniciada! Sigue el progreso en tiempo real en la consola."
        "</div>"
    )


@router.post("/partials/save-category-order", response_class=HTMLResponse)
async def partial_guardar_orden_categorias(request: Request):
    """Guarda en tiempo real el orden de las categorías desde la configuración."""
    form_data = await request.form()
    categories_order = form_data.getlist("category_order")

    if categories_order:
        save_categories_config(categories_order, categories_order)
        return HTMLResponse(
            "<span class='text-success small animate-fade'><i class='bi bi-check2-circle'></i> Orden guardado correctamente</span>"
        )
    return HTMLResponse(
        "<span class='text-warning small'>Sin cambios en el orden</span>"
    )


@router.get("/partials/verify-session", response_class=HTMLResponse)
async def partial_verificar_sesion(request: Request):
    """Verifica en tiempo real si la cookie configurada tiene acceso a SteamGifts."""
    if not settings.STEAMGIFTS_PHPSESSID:
        return templates.TemplateResponse(
            request=request,
            name="components/session_status.html",
            context={
                "success": False,
                "error": "La variable STEAMGIFTS_PHPSESSID está vacía. Configúrala en la pestaña de Configuración.",
            },
        )

    try:
        client = SteamGiftsClient(
            phpsessid=settings.STEAMGIFTS_PHPSESSID,
            base_url=settings.STEAMGIFTS_BASE_URL,
            user_agent=settings.USER_AGENT,
            timeout=settings.HTTP_TIMEOUT_SECONDS,
        )
        if not client.is_session_valid():
            return templates.TemplateResponse(
                request=request,
                name="components/session_status.html",
                context={
                    "success": False,
                    "error": "No se pudo validar la sesión. La cookie ha caducado o SteamGifts requiere verificación en el navegador.",
                },
            )
        info = client.get_account_info()
        return templates.TemplateResponse(
            request=request,
            name="components/session_status.html",
            context={"success": True, "account": info},
        )
    except Exception as e:
        logger.error(f"Error comprobando sesión: {e}")
        return templates.TemplateResponse(
            request=request,
            name="components/session_status.html",
            context={"success": False, "error": str(e)},
        )


@router.get("/partials/account-points", response_class=HTMLResponse)
async def partial_puntos_cuenta(request: Request):
    """Obtiene los puntos actualmente disponibles desde SteamGifts con botón de recarga."""
    if not settings.STEAMGIFTS_PHPSESSID:
        return templates.TemplateResponse(
            request=request,
            name="components/account_points.html",
            context={
                "configured": False,
                "error": "Cookie PHPSESSID no configurada.",
            },
        )

    try:
        client = SteamGiftsClient(
            phpsessid=settings.STEAMGIFTS_PHPSESSID,
            base_url=settings.STEAMGIFTS_BASE_URL,
            user_agent=settings.USER_AGENT,
            timeout=settings.HTTP_TIMEOUT_SECONDS,
        )
        if not client.is_session_valid():
            return templates.TemplateResponse(
                request=request,
                name="components/account_points.html",
                context={
                    "configured": True,
                    "valid": False,
                    "error": "Sesión inválida o expirada. Actualiza tu PHPSESSID.",
                },
            )

        acc = client.get_account_info()

        # Si alcanza o supera el umbral configurado (ej. 400), comprobar alerta Telegram
        from app.services.telegram_alert import notify_points_threshold_exceeded
        if acc.points >= settings.TELEGRAM_POINTS_THRESHOLD:
            notify_points_threshold_exceeded(acc.points, acc.username)

        return templates.TemplateResponse(
            request=request,
            name="components/account_points.html",
            context={
                "configured": True,
                "valid": True,
                "points": acc.points,
                "username": acc.username,
                "level": acc.level,
                "threshold": settings.TELEGRAM_POINTS_THRESHOLD,
                "limit_reached": acc.points >= settings.TELEGRAM_POINTS_THRESHOLD,
            },
        )
    except Exception as e:
        logger.error(f"Error consultando puntos de cuenta: {e}")
        return templates.TemplateResponse(
            request=request,
            name="components/account_points.html",
            context={
                "configured": True,
                "valid": False,
                "error": f"Error al conectar con SteamGifts: {e}",
            },
        )


@router.post("/partials/test-telegram", response_class=HTMLResponse)
async def partial_probar_telegram():
    """Envía un mensaje de prueba al bot de Telegram configurado."""
    from app.services.telegram_alert import send_telegram_message

    if not settings.TELEGRAM_ALERTS_ENABLED:
        return HTMLResponse(
            "<div class='alert alert-warning py-2 mb-0 small animate-fade'>"
            "<i class='bi bi-exclamation-triangle me-1'></i> Las alertas de Telegram están desactivadas en la configuración."
            "</div>"
        )

    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return HTMLResponse(
            "<div class='alert alert-danger py-2 mb-0 small animate-fade'>"
            "<i class='bi bi-x-circle me-1'></i> Falta configurar el TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID."
            "</div>"
        )

    msg = (
        "🤖 <b>SteamGifts Bot — Prueba de Conexión</b>\n\n"
        "¡Excelente! La integración de alertas de Telegram está funcionando correctamente.\n"
        f"Recibirás avisos automáticos cuando tus puntos alcancen o superen los <b>{settings.TELEGRAM_POINTS_THRESHOLD} P</b>."
    )

    exito = send_telegram_message(msg)
    if exito:
        return HTMLResponse(
            "<div class='alert alert-success py-2 mb-0 small animate-fade'>"
            "<i class='bi bi-check-circle me-1'></i> <strong>¡Mensaje enviado!</strong> Revisa tu Telegram, la prueba ha sido exitosa."
            "</div>"
        )
    else:
        return HTMLResponse(
            "<div class='alert alert-danger py-2 mb-0 small animate-fade'>"
            "<i class='bi bi-x-circle me-1'></i> No se pudo enviar el mensaje a Telegram. Verifica el token y chat ID."
            "</div>"
        )

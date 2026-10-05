"""Rutas web del frontend: vistas HTML y endpoints parciales renderizados con Jinja2 y HTMX."""

import html
import logging
import math
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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
from app.services.points_checker import points_checker
from app.services.steamgifts_client import SteamGiftsClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Web"])

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)


# ─── Vistas principales ──────────────────────────────────────────────

@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Sirve el favicon SVG para navegadores que solicitan /favicon.ico."""
    favicon_path = os.path.join(os.path.dirname(__file__), "static", "img", "favicon.svg")
    return FileResponse(favicon_path, media_type="image/svg+xml")


@router.get("/", response_class=HTMLResponse)
async def raiz():
    """Redirige la raíz al panel de control."""
    return RedirectResponse(url="/dashboard")


def _obtener_lista_categorias_configuradas() -> list:
    """Devuelve la lista ordenada y enriquecida de categorías para vistas y formularios."""
    order, _ = load_categories_config()
    categories_list = []
    for idx, cat_id in enumerate(order, start=1):
        info = AVAILABLE_CATEGORIES.get(cat_id, {})
        categories_list.append({
            "id": cat_id,
            "name": info.get("name", cat_id),
            "label": f"{idx}. {info.get('label', cat_id)}",
            "simple_label": f"{idx}. {info.get('name', cat_id)}",
            "raw_label": info.get("label", cat_id),
            "badge_class": info.get("badge_class", f"badge-{cat_id}"),
            "svg_icon": info.get("svg_icon", ""),
            "priority": idx,
        })
    return categories_list


def _obtener_cookie_enmascarada() -> str:
    """Devuelve la cookie PHPSESSID oculta parcialmente para privacidad."""
    cookie = settings.STEAMGIFTS_PHPSESSID
    if not cookie:
        return ""
    visible = min(8, len(cookie))
    return cookie[:visible] + "•" * max(0, len(cookie) - visible)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Vista principal: panel de control con métricas precargadas instantáneamente."""
    configured_categories = _obtener_lista_categorias_configuradas()
    is_running = getattr(main_app, "is_bot_running", False)

    # Carga instantánea de métricas locales sin peticiones externas
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

    # Carga de las 5 últimas sesiones de ejecución
    runs = (
        db.query(RunLog)
        .options(joinedload(RunLog.entries))
        .order_by(RunLog.started_at.desc())
        .limit(5)
        .all()
    )

    known_points = ultima_run.final_points if (ultima_run and ultima_run.final_points is not None) else None

    # Estado del chequeador automático de puntos
    checker_status = points_checker.get_status()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "title": "Dashboard",
            "categories": configured_categories,
            "is_running": is_running,
            "total_entradas": total_entradas,
            "total_puntos": total_puntos,
            "entradas_hoy": entradas_hoy,
            "ultima_run": ultima_run,
            "runs": runs,
            "known_points": known_points,
            "threshold": settings.TELEGRAM_POINTS_THRESHOLD,
            "checker": checker_status,
        },
    )


@router.get("/entries", response_class=HTMLResponse)
async def historial(request: Request, db: Session = Depends(get_db)):
    """Vista del historial de entradas con precarga instantánea de la primera página."""
    per_page = 15
    query = db.query(Entry)
    total_count = query.count()
    total_pages = max(1, math.ceil(total_count / per_page))
    entries = query.order_by(Entry.timestamp.desc()).limit(per_page).all()
    start_p = 1
    end_p = min(total_pages, 5)
    page_numbers = list(range(start_p, end_p + 1))
    start_idx = 1 if total_count > 0 else 0
    end_idx = min(per_page, total_count)

    return templates.TemplateResponse(
        request=request,
        name="entries.html",
        context={
            "title": "Historial de Entradas",
            "entries": entries,
            "page": 1,
            "total_pages": total_pages,
            "total_count": total_count,
            "per_page": per_page,
            "page_numbers": page_numbers,
            "start_idx": start_idx,
            "end_idx": end_idx,
            "search": "",
            "category": "",
            "run_id": None,
        },
    )


@router.get("/runs", response_class=HTMLResponse)
async def ejecuciones(request: Request, db: Session = Depends(get_db)):
    """Vista de ejecuciones pasadas del bot con precarga instantánea."""
    per_page = 15
    query = db.query(RunLog)
    total_count = query.count()
    total_pages = max(1, math.ceil(total_count / per_page))
    runs = query.order_by(RunLog.started_at.desc()).limit(per_page).all()
    start_p = 1
    end_p = min(total_pages, 5)
    page_numbers = list(range(start_p, end_p + 1))
    start_idx = 1 if total_count > 0 else 0
    end_idx = min(per_page, total_count)

    return templates.TemplateResponse(
        request=request,
        name="runs.html",
        context={
            "title": "Ejecuciones",
            "runs": runs,
            "page": 1,
            "total_pages": total_pages,
            "total_count": total_count,
            "per_page": per_page,
            "page_numbers": page_numbers,
            "start_idx": start_idx,
            "end_idx": end_idx,
        },
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
    return templates.TemplateResponse(
        request=request,
        name="config.html",
        context={
            "title": "Configuración",
            "settings": settings,
            "cookie_oculta": _obtener_cookie_enmascarada(),
            "categories": _obtener_lista_categorias_configuradas(),
            "checker": points_checker.get_status(),
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
    """Fragmento HTML con las sesiones de ejecución en formato de una línea (máx 5)."""
    runs = (
        db.query(RunLog)
        .options(joinedload(RunLog.entries))
        .order_by(RunLog.started_at.desc())
        .limit(5)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="components/execution_sessions.html",
        context={"runs": runs},
    )


@router.get("/partials/config-modal", response_class=HTMLResponse)
async def partial_config_modal(request: Request):
    """Fragmento HTML con el contenido de configuración para el modal."""
    return templates.TemplateResponse(
        request=request,
        name="components/config_form.html",
        context={
            "settings": settings,
            "cookie_oculta": _obtener_cookie_enmascarada(),
            "categories": _obtener_lista_categorias_configuradas(),
            "checker": points_checker.get_status(),
        },
    )


@router.get("/partials/console-logs", response_class=HTMLResponse)
async def partial_console_logs():
    """Fragmento HTML con los logs de la consola en tiempo real precedidos por el estado del sistema."""
    status_text = points_checker.get_summary_text()
    now_str = datetime.now().strftime("%H:%M:%S")
    time_html = f'<span class="console-time text-nowrap font-monospace" style="display:inline-block; width:68px; color:#64748b; font-size:0.76rem; flex-shrink:0;">[{now_str}]</span>'
    
    if points_checker.enabled:
        badge_style = "display:inline-block; width:100px; text-align:center; font-size:0.72rem; font-weight:700; border-radius:3px; padding:1px 0; margin-right:8px; flex-shrink:0; background:rgba(102,192,244,0.15); color:#66c0f4; border:1px solid rgba(102,192,244,0.35);"
        badge_html = f'<span class="console-badge" style="{badge_style}">SISTEMA</span>'
        color_text = "color: #93c5fd;"
    else:
        badge_style = "display:inline-block; width:100px; text-align:center; font-size:0.72rem; font-weight:700; border-radius:3px; padding:1px 0; margin-right:8px; flex-shrink:0; background:#19222e; color:#8f98a0; border:1px solid #2a475e;"
        badge_html = f'<span class="console-badge" style="{badge_style}">SISTEMA</span>'
        color_text = "color: #8f98a0;"

    header_line = f'<div class="console-line pb-1 mb-2 border-bottom" style="border-color: #243547 !important;">{time_html} {badge_html}<span style="{color_text} font-weight:600;">{html.escape(status_text)}</span></div>'

    html_logs = console_handler.get_formatted_html()
    if not console_handler.logs:
        contenido = f'{header_line}\n<div class="console-line text-muted fst-italic">consola@steamgifts-bot:~$ Sistema en espera. Pulsa "Iniciar Ejecución" para comenzar manualmente.</div>'
    else:
        contenido = f"{header_line}\n{html_logs}"

    is_running = getattr(main_app, "is_bot_running", False)
    if is_running:
        contenido += '\n<div class="console-line text-warning"><span class="spinner-border spinner-border-sm me-1"></span> Ejecutando bot en segundo plano... <span class="blink">▌</span></div>'

    return HTMLResponse(contenido)


@router.post("/partials/clear-console", response_class=HTMLResponse)
async def partial_clear_console():
    """Limpia el buffer de la consola web manteniendo la línea de estado del sistema."""
    console_handler.clear()
    status_text = points_checker.get_summary_text()
    now_str = datetime.now().strftime("%H:%M:%S")
    time_html = f'<span class="console-time text-nowrap font-monospace" style="display:inline-block; width:68px; color:#64748b; font-size:0.76rem; flex-shrink:0;">[{now_str}]</span>'
    badge_style = "display:inline-block; width:100px; text-align:center; font-size:0.72rem; font-weight:700; border-radius:3px; padding:1px 0; margin-right:8px; flex-shrink:0; background:#19222e; color:#8f98a0; border:1px solid #2a475e;"
    badge_html = f'<span class="console-badge" style="{badge_style}">SISTEMA</span>'
    header_line = f'<div class="console-line pb-1 mb-2 border-bottom" style="border-color: #243547 !important;">{time_html} {badge_html}<span style="color:#93c5fd; font-weight:600;">{html.escape(status_text)}</span></div>'
    return HTMLResponse(f'{header_line}\n<div class="console-line text-muted fst-italic">consola@steamgifts-bot:~$ Consola limpiada.</div>')


@router.post("/partials/save-config", response_class=HTMLResponse)
async def partial_save_config(request: Request):
    """Guarda la configuración general, del autochecker y el orden de categorías desde la app."""
    form_data = await request.form()

    phpsessid = str(form_data.get("phpsessid", "")).strip()
    max_entries = str(form_data.get("max_entries_per_run", "25")).strip()
    timeout = str(form_data.get("http_timeout_seconds", "15.0")).strip()
    min_delay = str(form_data.get("min_delay_seconds", "3.0")).strip()
    max_delay = str(form_data.get("max_delay_seconds", "8.0")).strip()
    category_delay = str(form_data.get("category_delay_seconds", "5.0")).strip()

    updates = {}
    if phpsessid and "•" not in phpsessid and "*" not in phpsessid:
        updates["STEAMGIFTS_PHPSESSID"] = phpsessid
    if max_entries.isdigit():
        updates["MAX_ENTRIES_PER_RUN"] = int(max_entries)
    try:
        updates["HTTP_TIMEOUT_SECONDS"] = float(int(float(timeout)))
        updates["MIN_DELAY_SECONDS"] = float(int(float(min_delay)))
        updates["MAX_DELAY_SECONDS"] = float(int(float(max_delay)))
        updates["CATEGORY_DELAY_SECONDS"] = float(int(float(category_delay)))
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

    # Parámetros de Autocheck / Chequeador de puntos
    autocheck_enabled = "autocheck_enabled" in form_data
    try:
        checker_updates = {
            "enabled": autocheck_enabled,
        }
        min_int = form_data.get("autocheck_min_interval")
        if min_int and str(min_int).isdigit():
            checker_updates["min_interval"] = int(min_int)
        max_int = form_data.get("autocheck_max_interval")
        if max_int and str(max_int).isdigit():
            checker_updates["max_interval"] = int(max_int)
        night_s = form_data.get("autocheck_night_start")
        if night_s and str(night_s).isdigit():
            checker_updates["night_start"] = int(night_s)
        night_e = form_data.get("autocheck_night_end")
        if night_e and str(night_e).isdigit():
            checker_updates["night_end"] = int(night_e)
        
        checker_updates["autorun_enabled"] = "autocheck_autorun_enabled" in form_data
        autorun_pts = form_data.get("autocheck_autorun_min_points")
        if autorun_pts and str(autorun_pts).isdigit():
            checker_updates["autorun_min_points"] = int(autorun_pts)

        points_checker.update_config(**checker_updates)

        if autocheck_enabled and not points_checker.is_running:
            points_checker.start()
        elif not autocheck_enabled and points_checker.is_running:
            points_checker.stop()
    except Exception as e:
        logger.warning(f"Error actualizando configuración del autochecker: {e}")

    # Guardar orden de categorías
    categories_order = form_data.getlist("category_order")
    if categories_order:
        save_categories_config(categories_order, categories_order)

    resp = HTMLResponse(
        "<div class='alert alert-success d-flex align-items-center py-2 px-3 mb-0 shadow-sm animate-fade' style='background: rgba(92, 126, 16, 0.2); border: 1px solid #7eb318; color: #a4d007;'>"
        "<i class='bi bi-check-circle-fill me-2 fs-5'></i>"
        "<div><strong>¡Configuración guardada!</strong> Los parámetros generales, el sistema de autochequeo, las alertas de Telegram y el orden de categorías han sido actualizados con éxito.</div>"
        "</div>"
    )
    resp.headers["HX-Trigger"] = '{"refreshAutocheck": true, "refreshAccount": true, "refreshStats": true}'
    return resp


@router.get("/partials/entries-table", response_class=HTMLResponse)
async def partial_tabla_entradas(
    request: Request,
    search: Optional[str] = None,
    category: Optional[str] = None,
    run_id: Optional[int] = None,
    page: int = 1,
    per_page: int = 15,
    db: Session = Depends(get_db),
):
    """Fragmento HTML con tabla filtrable por nombre/categoría y paginada sin scrollbars."""
    query = db.query(Entry)

    # Buscador por nombre de juego
    if search and search.strip():
        query = query.filter(Entry.game_name.ilike(f"%{search.strip()}%"))

    # Filtro por categoría
    if category and category.strip():
        query = query.filter(Entry.category == category.strip())

    # Filtro por sesión de ejecución si se especifica
    if run_id:
        query = query.filter(Entry.run_id == run_id)

    total_count = query.count()
    total_pages = max(1, math.ceil(total_count / per_page))

    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page
    entries = (
        query.order_by(Entry.timestamp.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    # Rango de números de página para paginador (máx 5 páginas)
    start_p = max(1, page - 2)
    end_p = min(total_pages, page + 2)
    page_numbers = list(range(start_p, end_p + 1))

    # Rango visible de registros (ej. 1 a 12 de 45)
    start_idx = offset + 1 if total_count > 0 else 0
    end_idx = min(offset + per_page, total_count)

    return templates.TemplateResponse(
        request=request,
        name="components/entries_table.html",
        context={
            "entries": entries,
            "page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "per_page": per_page,
            "page_numbers": page_numbers,
            "start_idx": start_idx,
            "end_idx": end_idx,
            "search": search or "",
            "category": category or "",
            "run_id": run_id,
        },
    )


@router.get("/partials/runs-table", response_class=HTMLResponse)
async def partial_tabla_ejecuciones(
    request: Request,
    page: int = 1,
    per_page: int = 15,
    db: Session = Depends(get_db),
):
    """Fragmento HTML con la lista paginada de ejecuciones del bot (hasta 15 filas como Historial)."""
    query = db.query(RunLog)
    total_count = query.count()
    total_pages = max(1, math.ceil(total_count / per_page))

    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page
    runs = (
        query.order_by(RunLog.started_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    start_p = max(1, page - 2)
    end_p = min(total_pages, page + 2)
    page_numbers = list(range(start_p, end_p + 1))

    start_idx = offset + 1 if total_count > 0 else 0
    end_idx = min(offset + per_page, total_count)

    return templates.TemplateResponse(
        request=request,
        name="components/runs_table.html",
        context={
            "runs": runs,
            "page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "per_page": per_page,
            "page_numbers": page_numbers,
            "start_idx": start_idx,
            "end_idx": end_idx,
        },
    )


@router.get("/partials/runs/latest/modal", response_class=HTMLResponse)
async def partial_modal_ultima_ejecucion(
    request: Request,
    db: Session = Depends(get_db),
):
    """Fragmento HTML con el contenido completo del modal para la última ejecución realizada."""
    run = db.query(RunLog).order_by(RunLog.started_at.desc()).first()
    if not run:
        return HTMLResponse(
            "<div class='p-4 text-center text-muted'>No hay registros de ejecuciones todavía.</div>"
        )
    entries = db.query(Entry).filter(Entry.run_id == run.id).order_by(Entry.timestamp.asc()).all()
    return templates.TemplateResponse(
        request=request,
        name="components/run_detail_modal.html",
        context={"run": run, "entries": entries},
    )


@router.get("/partials/runs/{run_id}/modal", response_class=HTMLResponse)
async def partial_modal_ejecucion(
    request: Request,
    run_id: int,
    db: Session = Depends(get_db),
):
    """Fragmento HTML con el contenido completo para el modal de detalle de ejecución."""
    run = db.query(RunLog).filter(RunLog.id == run_id).first()
    if not run:
        return HTMLResponse(
            "<div class='p-4 text-center text-muted'>Ejecución no encontrada.</div>"
        )
    entries = db.query(Entry).filter(Entry.run_id == run_id).order_by(Entry.timestamp.asc()).all()
    return templates.TemplateResponse(
        request=request,
        name="components/run_detail_modal.html",
        context={"run": run, "entries": entries},
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
        resp = HTMLResponse("")
        resp.headers["HX-Trigger"] = '{"showToast": {"message": "El bot ya está ejecutándose en segundo plano.", "type": "warning"}}'
        return resp

    if not settings.STEAMGIFTS_PHPSESSID:
        resp = HTMLResponse("")
        resp.headers["HX-Trigger"] = '{"showToast": {"message": "Cookie PHPSESSID no configurada. Ve a Configuración.", "type": "danger"}}'
        return resp

    order, _ = load_categories_config()
    background_tasks.add_task(_ejecutar_bot_en_segundo_plano, order)
    resp = HTMLResponse("")
    resp.headers["HX-Trigger"] = (
        '{"showToast": {"message": "¡Ejecución iniciada! Procesando sorteos en segundo plano...", "type": "success"}, '
        '"refreshStats": true, "refreshSessions": true, "refreshAccount": true}'
    )
    return resp


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
        valida, motivo = client.check_session()
        if not valida:
            return templates.TemplateResponse(
                request=request,
                name="components/session_status.html",
                context={
                    "success": False,
                    "error": motivo,
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
        acc = client.get_account_info()

        if not acc or acc.username == "Desconocido":
            return templates.TemplateResponse(
                request=request,
                name="components/account_points.html",
                context={
                    "configured": True,
                    "valid": False,
                    "error": "Sesión inválida o expirada. Actualiza tu PHPSESSID.",
                },
            )

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


# --- Endpoints del Chequeador Automatico de Puntos ---

@router.post('/partials/autocheck-toggle', response_class=HTMLResponse)
async def partial_autocheck_toggle(request: Request):
    if points_checker.is_running:
        points_checker.stop()
    else:
        points_checker.start()
    resp = templates.TemplateResponse(
        request=request,
        name='components/autocheck_status.html',
        context={'checker': points_checker.get_status()},
    )
    resp.headers["HX-Trigger"] = '{"refreshAccount": true, "refreshStats": true}'
    return resp


@router.post('/partials/autocheck-config', response_class=HTMLResponse)
async def partial_autocheck_config(request: Request):
    form_data = await request.form()
    updates = {}
    autorun_raw = form_data.get('autorun_enabled')
    if autorun_raw is not None:
        updates['autorun_enabled'] = autorun_raw.lower() in ('true', '1', 'on')
    min_points_raw = form_data.get('autorun_min_points')
    if min_points_raw and min_points_raw.isdigit():
        val = int(min_points_raw)
        if 50 <= val <= 500:
            updates['autorun_min_points'] = val
    min_interval_raw = form_data.get('min_interval')
    if min_interval_raw and min_interval_raw.isdigit():
        val = int(min_interval_raw)
        if 5 <= val <= 300:
            updates['min_interval'] = val
    max_interval_raw = form_data.get('max_interval')
    if max_interval_raw and max_interval_raw.isdigit():
        val = int(max_interval_raw)
        if 10 <= val <= 600:
            updates['max_interval'] = val
    if updates:
        points_checker.update_config(**updates)
    resp = templates.TemplateResponse(
        request=request,
        name='components/autocheck_status.html',
        context={'checker': points_checker.get_status()},
    )
    resp.headers["HX-Trigger"] = '{"refreshAccount": true, "refreshStats": true}'
    return resp


@router.get('/partials/autocheck-status', response_class=HTMLResponse)
async def partial_autocheck_status(request: Request):
    return templates.TemplateResponse(
        request=request,
        name='components/autocheck_status.html',
        context={'checker': points_checker.get_status()},
    )

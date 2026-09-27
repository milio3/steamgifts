"""Rutas web del frontend: vistas HTML y endpoints parciales renderizados con Jinja2 y HTMX."""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

import app.main as main_app
from app.api.v1.bot import _ejecutar_bot_en_segundo_plano
from app.core.config import settings
from app.core.database import get_db
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
    """Vista principal: panel de control con métricas y controles."""
    return templates.TemplateResponse(
        request=request, name="dashboard.html", context={"title": "Dashboard"}
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
    """Vista de configuración (solo lectura y verificación de credencial)."""
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


@router.get("/partials/latest-entries", response_class=HTMLResponse)
async def partial_ultimas_entradas(request: Request, db: Session = Depends(get_db)):
    """Fragmento HTML con las últimas 10 entradas para el panel principal."""
    entries = db.query(Entry).order_by(Entry.timestamp.desc()).limit(10).all()
    return templates.TemplateResponse(
        request=request,
        name="components/entries_table.html",
        context={"entries": entries},
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
    """Gestiona el formulario web para lanzar la ejecución del bot en segundo plano."""
    if getattr(main_app, "is_bot_running", False):
        return HTMLResponse(
            "<div class='alert alert-warning py-2 mb-0 small'><i class='bi bi-exclamation-triangle'></i> El bot ya está en ejecución.</div>"
        )

    if not settings.STEAMGIFTS_PHPSESSID:
        return HTMLResponse(
            "<div class='alert alert-danger py-2 mb-0 small'><i class='bi bi-x-circle'></i> Cookie PHPSESSID no configurada en .env</div>"
        )

    form_data = await request.form()
    categories = form_data.getlist("categories")
    if not categories:
        categories = None

    background_tasks.add_task(_ejecutar_bot_en_segundo_plano, categories)
    return HTMLResponse(
        "<div class='alert alert-success py-2 mb-0 small'><i class='bi bi-check-circle'></i> ¡Ejecución iniciada correctamente!</div>"
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
                "error": "La variable STEAMGIFTS_PHPSESSID está vacía en el fichero .env.",
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

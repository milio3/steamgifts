"""Endpoints API para consultar entradas, ejecuciones y estadísticas."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.entry import Entry, RunLog

router = APIRouter(prefix="/api/v1/entries", tags=["Entradas"])


@router.get("/")
def listar_entradas(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    category: Optional[str] = None,
    result: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Lista entradas con paginación y filtros opcionales."""
    query = db.query(Entry)

    if category:
        query = query.filter(Entry.category == category)
    if result:
        query = query.filter(Entry.result == result)

    total = query.count()
    entries = query.order_by(Entry.timestamp.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "entries": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "game_name": e.game_name,
                "giveaway_code": e.giveaway_code,
                "giveaway_url": e.giveaway_url,
                "category": e.category,
                "points_spent": e.points_spent,
                "points_remaining": e.points_remaining,
                "entries_count": e.entries_count,
                "copies": e.copies,
                "result": e.result,
                "error_message": e.error_message,
                "time_remaining": e.time_remaining,
                "run_id": e.run_id,
            }
            for e in entries
        ],
    }


@router.get("/stats")
def obtener_estadisticas(db: Session = Depends(get_db)):
    """Devuelve estadísticas generales y por categoría."""
    total_entradas = db.query(Entry).filter(Entry.result == "success").count()
    total_puntos = (
        db.query(func.sum(Entry.points_spent))
        .filter(Entry.result == "success")
        .scalar()
        or 0
    )

    # Entradas de hoy
    hoy = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    entradas_hoy = (
        db.query(Entry)
        .filter(Entry.result == "success", Entry.timestamp >= hoy)
        .count()
    )

    # Entradas por categoría
    por_categoria = (
        db.query(Entry.category, func.count(Entry.id))
        .filter(Entry.result == "success")
        .group_by(Entry.category)
        .all()
    )

    # Entradas por día (últimos 30 días)
    hace_30_dias = datetime.now(timezone.utc) - timedelta(days=30)
    por_dia = (
        db.query(
            func.date(Entry.timestamp).label("fecha"),
            func.count(Entry.id).label("total"),
        )
        .filter(Entry.result == "success", Entry.timestamp >= hace_30_dias)
        .group_by(func.date(Entry.timestamp))
        .order_by(func.date(Entry.timestamp).desc())
        .all()
    )

    # Total de ejecuciones
    total_ejecuciones = db.query(RunLog).count()

    # Última ejecución
    ultima_ejecucion = (
        db.query(RunLog).order_by(RunLog.started_at.desc()).first()
    )

    # Juegos más frecuentes
    juegos_top = (
        db.query(Entry.game_name, func.count(Entry.id).label("veces"))
        .filter(Entry.result == "success")
        .group_by(Entry.game_name)
        .order_by(func.count(Entry.id).desc())
        .limit(10)
        .all()
    )

    return {
        "total_entradas": total_entradas,
        "total_puntos_gastados": total_puntos,
        "entradas_hoy": entradas_hoy,
        "total_ejecuciones": total_ejecuciones,
        "ultima_ejecucion": {
            "id": ultima_ejecucion.id,
            "fecha": ultima_ejecucion.started_at.isoformat() if ultima_ejecucion.started_at else None,
            "estado": ultima_ejecucion.status,
            "entradas": ultima_ejecucion.total_entries,
        }
        if ultima_ejecucion
        else None,
        "por_categoria": {cat: count for cat, count in por_categoria},
        "por_dia": [
            {"fecha": str(fecha), "total": total} for fecha, total in por_dia
        ],
        "juegos_top": [
            {"juego": nombre, "veces": veces} for nombre, veces in juegos_top
        ],
    }


@router.get("/runs")
def listar_ejecuciones(
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Lista las ejecuciones del bot con paginación."""
    total = db.query(RunLog).count()
    runs = (
        db.query(RunLog)
        .order_by(RunLog.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "runs": [
            {
                "id": r.id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "total_entries": r.total_entries,
                "total_points_spent": r.total_points_spent,
                "initial_points": r.initial_points,
                "final_points": r.final_points,
                "status": r.status,
                "error_message": r.error_message,
            }
            for r in runs
        ],
    }


@router.get("/runs/{run_id}")
def detalle_ejecucion(run_id: int, db: Session = Depends(get_db)):
    """Devuelve el detalle de una ejecución con todas sus entradas."""
    run = db.query(RunLog).filter(RunLog.id == run_id).first()
    if not run:
        return {"error": "Ejecución no encontrada"}

    entries = (
        db.query(Entry)
        .filter(Entry.run_id == run_id)
        .order_by(Entry.timestamp.asc())
        .all()
    )

    return {
        "run": {
            "id": run.id,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "total_entries": run.total_entries,
            "total_points_spent": run.total_points_spent,
            "initial_points": run.initial_points,
            "final_points": run.final_points,
            "status": run.status,
            "error_message": run.error_message,
        },
        "entries": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                "game_name": e.game_name,
                "giveaway_code": e.giveaway_code,
                "category": e.category,
                "points_spent": e.points_spent,
                "result": e.result,
                "error_message": e.error_message,
            }
            for e in entries
        ],
    }

"""Endpoints de salud y disponibilidad de la aplicación."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine

router = APIRouter(tags=["Salud"])


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Verificación de vitalidad (liveness). Siempre responde si el proceso está vivo."""
    return {"status": "ok", "version": settings.VERSION}


@router.get("/ready", status_code=status.HTTP_200_OK)
def ready_check():
    """Verificación de disponibilidad (readiness). Comprueba la conexión a BD."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unready", "database_error": str(e)},
        )

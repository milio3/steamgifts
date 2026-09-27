"""Modelos SQLAlchemy para el registro de participaciones y ejecuciones del bot."""

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


def _ahora_utc():
    """Retorna la fecha y hora actual en UTC para default en columnas."""
    return datetime.now(timezone.utc)


class RunLog(Base):
    """Registro de una ronda o ejecución completa del bot."""

    __tablename__ = "run_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, default=_ahora_utc)
    finished_at = Column(DateTime, nullable=True)
    total_entries = Column(Integer, default=0)
    total_points_spent = Column(Integer, default=0)
    initial_points = Column(Integer, nullable=True)
    final_points = Column(Integer, nullable=True)
    status = Column(String(20), default="running")  # running, completed, error
    error_message = Column(String(500), nullable=True)

    entries = relationship("Entry", back_populates="run_log")


class Entry(Base):
    """Registro individual de una participación en un sorteo."""

    __tablename__ = "entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=_ahora_utc)
    game_name = Column(String(500), nullable=False)
    giveaway_code = Column(String(10), nullable=False)
    giveaway_url = Column(String(500), nullable=True)
    category = Column(String(50), nullable=False)
    points_spent = Column(Integer, nullable=False, default=0)
    points_remaining = Column(Integer, nullable=True)
    entries_count = Column(Integer, nullable=True, default=0)
    copies = Column(Integer, default=1)
    result = Column(String(20), nullable=False)  # success, error, skipped
    error_message = Column(String(500), nullable=True)
    time_remaining = Column(String(100), nullable=True)

    run_id = Column(Integer, ForeignKey("run_logs.id"), nullable=True)
    run_log = relationship("RunLog", back_populates="entries")

"""Configuración de base de datos SQLite con SQLAlchemy y modo WAL."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

# Motor SQLAlchemy con SQLite y timeout de 15 segundos
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 15},
)


@event.listens_for(engine, "connect")
def _configurar_pragma_sqlite(dbapi_connection, connection_record):
    """Activa modo WAL y synchronous=NORMAL en cada conexión SQLite."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency de FastAPI para obtener una sesión de BD."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

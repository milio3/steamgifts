"""Punto de entrada principal de la aplicación SteamGifts Bot."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text

from app.core.config import settings
from app.core.database import Base, engine
from app.core.logging_buffer import console_handler, setup_file_logging

# Configuración de logging en consola y buffer web
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.root.addHandler(console_handler)
# Configurar archivo de log persistente (logs/steamgifts_bot.log)
setup_file_logging()
logger = logging.getLogger(__name__)

# Variable global para estado del bot
is_bot_running = False


def _ejecutar_migraciones_bd():
    """Aplica migraciones automáticas si la BD proviene de una versión anterior."""
    try:
        with engine.connect() as conn:
            # Comprobar si la tabla run_logs existe y tiene la columna trigger_type
            result = conn.execute(text("PRAGMA table_info(run_logs);")).fetchall()
            if result:
                columnas = [row[1] for row in result]
                if "trigger_type" not in columnas:
                    conn.execute(text("ALTER TABLE run_logs ADD COLUMN trigger_type VARCHAR(20) DEFAULT 'manual';"))
                    conn.commit()
                    logger.info("✅ Migración aplicada con éxito: columna 'trigger_type' añadida a 'run_logs'")
    except Exception as e:
        logger.warning(f"Aviso al comprobar migraciones de BD: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación: crea tablas al arrancar e inicia el autochecker si procede."""
    # Crear directorio de datos si no existe
    Path("data").mkdir(exist_ok=True)
    # Crear tablas en BD al arrancar
    Base.metadata.create_all(bind=engine)
    # Aplicar migraciones automáticas en BD preexistentes
    _ejecutar_migraciones_bd()
    logger.info("Aplicación iniciada - Tablas de BD verificadas")

    # Arrancar el chequeador automático de puntos si estaba habilitado
    from app.services.points_checker import points_checker
    points_checker.auto_start_if_enabled()

    yield

    # Detener el chequeador al apagar la app
    if points_checker.is_running:
        points_checker.stop()
    logger.info("Aplicación detenida")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers API
from app.api import health  # noqa: E402
from app.api.v1 import bot, entries  # noqa: E402

app.include_router(health.router)
app.include_router(bot.router)
app.include_router(entries.router)

# Rutas web (frontend)
WEB_DIR = Path(__file__).parent / "web"
STATIC_DIR = WEB_DIR / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    logger.info("Directorio de ficheros estáticos montado en /static")

# Importar rutas web si existen
try:
    from app.web.routes import router as web_router  # noqa: E402
    app.include_router(web_router)
    logger.info("Rutas web cargadas correctamente")
except ImportError:
    logger.warning("Módulo web no encontrado, solo API disponible")

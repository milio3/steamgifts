"""Punto de entrada principal de la aplicación SteamGifts Bot."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import Base, engine

# Configuración de logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Variable global para estado del bot
is_bot_running = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación: crea tablas al arrancar."""
    # Crear directorio de datos si no existe
    Path("data").mkdir(exist_ok=True)
    # Crear tablas en BD al arrancar
    Base.metadata.create_all(bind=engine)
    logger.info("Aplicación iniciada - Tablas de BD verificadas")
    yield
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

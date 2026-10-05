"""Configuración centralizada y gestión de variables de entorno de SteamGifts Bot."""

import os
from pathlib import Path
from typing import Any, Dict

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Rutas estándar de los ficheros de entorno
ENV_DESA_PATH = Path(".env.desa")
ENV_PROD_PATH = Path(".env")
ACTIVE_ENV_PATH = ENV_DESA_PATH if ENV_DESA_PATH.exists() else ENV_PROD_PATH


class Settings(BaseSettings):
    """Configuración centralizada de la aplicación con validación de tipos Pydantic."""

    PROJECT_NAME: str = "SteamGifts Bot"
    VERSION: str = "2.2.3"
    PORT: int = 8090
    DEBUG: bool = False
    DATABASE_URL: str = "sqlite:///data/database.db"
    STEAMGIFTS_PHPSESSID: str = ""
    STEAMGIFTS_BASE_URL: str = "https://www.steamgifts.com"
    HTTP_TIMEOUT_SECONDS: float = 15.0
    MIN_DELAY_SECONDS: float = 3.0
    MAX_DELAY_SECONDS: float = 8.0
    MAX_ENTRIES_PER_RUN: int = 25
    CATEGORY_DELAY_SECONDS: float = 5.0
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )

    # Alertas de Telegram (Límite de puntos alcanzado)
    TELEGRAM_ALERTS_ENABLED: bool = False
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    TELEGRAM_POINTS_THRESHOLD: int = 400

    # Chequeo automático de puntos y auto-ejecución
    AUTOCHECK_ENABLED: bool = True
    AUTOCHECK_MIN_INTERVAL: int = 60
    AUTOCHECK_MAX_INTERVAL: int = 120
    AUTOCHECK_NIGHT_START: int = 1
    AUTOCHECK_NIGHT_END: int = 9
    AUTOCHECK_AUTORUN_ENABLED: bool = True
    AUTOCHECK_AUTORUN_MIN_POINTS: int = 380

    # Prioridad y orden de categorías (separadas por coma, formato canónico en minúsculas)
    CATEGORIES_ORDER: str = "wishlist,dlc,group,multiple_copies,recommended,new,all"

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def normalizar_database_url(cls, v: str) -> str:
        """Si la ruta de SQLite es de contenedor (/app/data) pero estamos en local, adaptar a data/database.db."""
        if "/app/data" in v and not os.path.exists("/app"):
            return "sqlite:///data/database.db"
        return v

    model_config = SettingsConfigDict(
        env_file=(".env.desa", ".env") if os.path.exists(".env.desa") else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def _formatear_linea_env(key: str, val: Any) -> str:
    """Devuelve una línea formateada adecuadamente para archivos .env."""
    if isinstance(val, bool):
        return f"{key}={str(val).lower()}\n"
    elif isinstance(val, str) and not (val.startswith('"') and val.endswith('"')):
        return f'{key}="{val}"\n'
    return f"{key}={val}\n"


def _es_cookie_invalida(cookie: str) -> bool:
    """Comprueba si el valor de cookie no debe persistirse por ser ficticio o inválido."""
    c = cookie.strip().strip('"').strip("'")
    return not c or "•" in c or any(pat in c.lower() for pat in ("testcookie", "cookie_test", "dummy"))


def _actualizar_archivo_env(env_path: Path, updates: Dict[str, Any]) -> None:
    """Actualiza o inserta las variables especificadas en el archivo .env indicado respetando comentarios."""
    env_lines = []
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                env_lines = f.readlines()
        except Exception:
            pass

    applied_keys = set()
    new_lines = []

    for line in env_lines:
        line_clean = line.strip()
        if "=" in line_clean and not line_clean.startswith("#"):
            key = line_clean.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(_formatear_linea_env(key, updates[key]))
                applied_keys.add(key)
                continue
        new_lines.append(line)

    # Claves nuevas que no existían previamente en el archivo
    for key, val in updates.items():
        if key not in applied_keys:
            new_lines.append(_formatear_linea_env(key, val))

    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception:
        pass


def update_settings_and_env(updates: Dict[str, Any]) -> bool:
    """Actualiza los parámetros en la instancia global settings y los persiste en disco (.env y .env.desa)."""
    # Filtrar cookies inválidas o ficticias
    if "STEAMGIFTS_PHPSESSID" in updates and _es_cookie_invalida(str(updates["STEAMGIFTS_PHPSESSID"])):
        del updates["STEAMGIFTS_PHPSESSID"]

    # Determinar ficheros de destino
    if str(ACTIVE_ENV_PATH).endswith(".test"):
        target_files = [ACTIVE_ENV_PATH]
    else:
        target_files = []
        if ENV_DESA_PATH.exists():
            target_files.append(ENV_DESA_PATH)
        if ENV_PROD_PATH.exists():
            target_files.append(ENV_PROD_PATH)
        if not target_files:
            target_files.append(ACTIVE_ENV_PATH)

    # Persistir en todos los ficheros destino
    for env_path in target_files:
        _actualizar_archivo_env(env_path, updates)

    # Actualizar valores en la instancia en memoria
    for k, v in updates.items():
        if hasattr(settings, k):
            curr_val = getattr(settings, k)
            if isinstance(curr_val, bool):
                if isinstance(v, bool):
                    setattr(settings, k, v)
                elif isinstance(v, str):
                    setattr(settings, k, v.lower() in ("true", "1", "yes"))
                else:
                    setattr(settings, k, bool(v))
            else:
                target_type = type(curr_val) if curr_val is not None else str
                try:
                    setattr(settings, k, target_type(v))
                except Exception:
                    setattr(settings, k, v)
    return True


# Instancia única global de configuración
settings = Settings()

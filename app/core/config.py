import os
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración centralizada de la aplicación SteamGifts Bot."""

    PROJECT_NAME: str = "SteamGifts Bot"
    VERSION: str = "2.1.1"
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

    # Prioridad y orden de categorías (separadas por coma)
    CATEGORIES_ORDER: str = "wishlist,dlc,group,Multiple Copies,recommended,new,all"

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def normalizar_database_url(cls, v: str) -> str:
        """Si la ruta de SQLite es de contenedor (/app/data) pero estamos en local, adaptar a data/database.db."""
        if "/app/data" in v and not os.path.exists("/app"):
            return "sqlite:///data/database.db"
        return v

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.desa") if os.path.exists(".env.desa") else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


from pathlib import Path

ACTIVE_ENV_PATH = Path(".env.desa") if Path(".env.desa").exists() else Path(".env")


def update_settings_and_env(updates: dict) -> bool:
    """Actualiza los parámetros en el objeto settings y los persiste en .env.desa y .env."""
    # Protección estricta: nunca sobrescribir STEAMGIFTS_PHPSESSID con valores ficticios de tests o vacíos
    if "STEAMGIFTS_PHPSESSID" in updates:
        val_cookie = str(updates["STEAMGIFTS_PHPSESSID"]).strip().strip('"').strip("'")
        if (
            not val_cookie
            or "•" in val_cookie
            or "testcookie" in val_cookie.lower()
            or "cookie_test" in val_cookie.lower()
            or "dummy" in val_cookie.lower()
        ):
            del updates["STEAMGIFTS_PHPSESSID"]

    if str(ACTIVE_ENV_PATH).endswith(".test"):
        target_files = [ACTIVE_ENV_PATH]
    else:
        target_files = []
        if Path(".env.desa").exists():
            target_files.append(Path(".env.desa"))
        if Path(".env").exists():
            target_files.append(Path(".env"))
        if not target_files:
            target_files.append(ACTIVE_ENV_PATH)

    def _formatear_linea(k: str, v) -> str:
        if isinstance(v, bool):
            return f"{k}={str(v).lower()}\n"
        elif isinstance(v, str) and not (v.startswith('"') and v.endswith('"')):
            return f'{k}="{v}"\n'
        else:
            return f"{k}={v}\n"

    for env_path in target_files:
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
                key = line_clean.split("=")[0].strip()
                if key in updates:
                    val = updates[key]
                    new_lines.append(_formatear_linea(key, val))
                    applied_keys.add(key)
                    continue
            new_lines.append(line)

        for key, val in updates.items():
            if key not in applied_keys:
                new_lines.append(_formatear_linea(key, val))

        try:
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception:
            pass

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


def _inicializar_settings() -> Settings:
    """Inicializa Settings priorizando los valores de .env.desa si existe."""
    s = Settings()
    desa = Path(".env.desa")
    if desa.exists():
        try:
            with open(desa, "r", encoding="utf-8") as f:
                for line in f:
                    line_s = line.strip()
                    if line_s and not line_s.startswith("#") and "=" in line_s:
                        k, v = line_s.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if hasattr(s, k) and v:
                            curr = getattr(s, k)
                            if isinstance(curr, bool):
                                setattr(s, k, v.lower() in ("true", "1", "yes"))
                            elif isinstance(curr, int):
                                setattr(s, k, int(v))
                            elif isinstance(curr, float):
                                setattr(s, k, float(v))
                            else:
                                setattr(s, k, v)
        except Exception:
            pass
    return s


settings = _inicializar_settings()


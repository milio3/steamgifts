from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración centralizada de la aplicación SteamGifts Bot."""

    PROJECT_NAME: str = "SteamGifts Bot"
    VERSION: str = "1.0.0"
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

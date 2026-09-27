"""Fixtures y configuración de pruebas con Pytest."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Genera una sesión de base de datos aislada en memoria para cada prueba."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Genera un cliente TestClient con la dependencia de base de datos sustituida."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def aislar_config_y_entorno(tmp_path, monkeypatch):
    """Aísla el fichero de configuración de categorías y los ficheros de entorno durante los tests."""
    import app.core.categories as cats_mod
    import app.core.config as cfg_mod

    test_file = tmp_path / "bot_config.json"
    monkeypatch.setattr(cats_mod, "CONFIG_PATH", test_file)

    test_env = tmp_path / ".env.test"
    test_env.write_text('STEAMGIFTS_PHPSESSID="dummy_test_cookie"\n', encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "ACTIVE_ENV_PATH", test_env)

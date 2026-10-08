"""Pruebas de persistencia unificada de parámetros en .env (autocheck, categorías y ejecución)."""

import os
from pathlib import Path
from app.core.config import settings, update_settings_and_env
from app.services.points_checker import PointsChecker
from app.core.categories import load_categories_config, save_categories_config


def test_update_settings_and_env_persists_autocheck_and_categories(tmp_path, monkeypatch):
    """Verifica que update_settings_and_env guarde tipos booleanos, numéricos y categorías en .env."""
    test_env = tmp_path / ".env.test"
    test_env.write_text("STEAMGIFTS_PHPSESSID=\"original_cookie\"\n", encoding="utf-8")

    import app.core.config as config_module
    monkeypatch.setattr(config_module, "ACTIVE_ENV_PATH", test_env)

    nuevos_valores = {
        "AUTOCHECK_ENABLED": True,
        "AUTOCHECK_MIN_INTERVAL": 45,
        "AUTOCHECK_MAX_INTERVAL": 95,
        "AUTOCHECK_NIGHT_START": 2,
        "AUTOCHECK_NIGHT_END": 8,
        "AUTOCHECK_AUTORUN_ENABLED": True,
        "AUTOCHECK_AUTORUN_MIN_POINTS": 370,
        "CATEGORIES_ORDER": "dlc,wishlist,group,multiple_copies,recommended,new,all",
    }

    resultado = update_settings_and_env(nuevos_valores)
    assert resultado is True

    # Verificar que settings en memoria se actualizó
    assert settings.AUTOCHECK_ENABLED is True
    assert settings.AUTOCHECK_MIN_INTERVAL == 45
    assert settings.AUTOCHECK_MAX_INTERVAL == 95
    assert settings.AUTOCHECK_NIGHT_START == 2
    assert settings.AUTOCHECK_NIGHT_END == 8
    assert settings.AUTOCHECK_AUTORUN_ENABLED is True
    assert settings.AUTOCHECK_AUTORUN_MIN_POINTS == 370
    assert settings.CATEGORIES_ORDER == "dlc,wishlist,group,multiple_copies,recommended,new,all"

    # Verificar contenido del fichero .env.test
    contenido = test_env.read_text(encoding="utf-8")
    assert "AUTOCHECK_ENABLED=true" in contenido
    assert "AUTOCHECK_MIN_INTERVAL=45" in contenido
    assert "AUTOCHECK_MAX_INTERVAL=95" in contenido
    assert "AUTOCHECK_NIGHT_START=2" in contenido
    assert "AUTOCHECK_NIGHT_END=8" in contenido
    assert "AUTOCHECK_AUTORUN_ENABLED=true" in contenido
    assert "AUTOCHECK_AUTORUN_MIN_POINTS=370" in contenido
    assert 'CATEGORIES_ORDER="dlc,wishlist,group,multiple_copies,recommended,new,all"' in contenido


def test_points_checker_persist_updates_env(tmp_path, monkeypatch):
    """Verifica que PointsChecker al actualizarse guarde su estado en .env."""
    test_env = tmp_path / ".env.test"
    test_env.write_text("", encoding="utf-8")

    import app.core.config as config_module
    monkeypatch.setattr(config_module, "ACTIVE_ENV_PATH", test_env)

    checker = PointsChecker()
    checker.update_config(
        enabled=False,
        min_interval=30,
        max_interval=75,
        autorun_enabled=False,
        autorun_min_points=390,
    )

    contenido = test_env.read_text(encoding="utf-8")
    assert "AUTOCHECK_ENABLED=false" in contenido
    assert "AUTOCHECK_MIN_INTERVAL=30" in contenido
    assert "AUTOCHECK_MAX_INTERVAL=75" in contenido
    assert "AUTOCHECK_AUTORUN_ENABLED=false" in contenido
    assert "AUTOCHECK_AUTORUN_MIN_POINTS=390" in contenido


def test_categories_save_and_load_with_env(tmp_path, monkeypatch):
    """Verifica que el orden de categorías se guarde en .env y se cargue correctamente."""
    test_env = tmp_path / ".env.test"
    test_env.write_text("", encoding="utf-8")

    import app.core.config as config_module
    monkeypatch.setattr(config_module, "ACTIVE_ENV_PATH", test_env)

    nuevo_orden = ["dlc", "wishlist", "group", "multiple_copies", "recommended", "new", "all"]
    exito = save_categories_config(nuevo_orden, nuevo_orden)
    assert exito is True

    contenido = test_env.read_text(encoding="utf-8")
    assert 'CATEGORIES_ORDER="dlc,wishlist,group,multiple_copies,recommended,new,all"' in contenido

    orden_cargado, habilitadas = load_categories_config()
    assert orden_cargado[0] == "dlc"
    assert orden_cargado[1] == "wishlist"
    assert "multiple_copies" in orden_cargado

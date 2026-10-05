"""Servicio de chequeo automático de puntos con jitter y restricción horaria nocturna."""

import json
import logging
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Ruta del fichero de persistencia de la configuración del autochecker
_CONFIG_FILE = Path("data/autocheck_config.json")

# Valores por defecto (activos tras cualquier despliegue o primera inicialización)
_DEFAULTS = {
    "enabled": True,
    "min_interval": 60,
    "max_interval": 120,
    "night_start": 1,
    "night_end": 9,
    "autorun_enabled": True,
    "autorun_min_points": 380,
}


def _load_config() -> dict:
    """Carga la configuración del autochecker desde disco, o devuelve los valores por defecto."""
    try:
        if _CONFIG_FILE.exists():
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Merge con defaults para campos nuevos
            merged = {**_DEFAULTS, **data}
            return merged
    except Exception as e:
        logger.warning(f"[AUTOCHECKER] Error cargando configuración: {e}. Usando valores por defecto.")
    return dict(_DEFAULTS)


def _save_config(cfg: dict) -> None:
    """Persiste la configuración del autochecker en disco."""
    try:
        _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[AUTOCHECKER] Error guardando configuración: {e}")


class PointsChecker:
    """Chequeador automático de puntos en segundo plano.

    Ejecuta un hilo daemon que periódicamente consulta los puntos disponibles en
    SteamGifts. Si se superan los puntos configurados, lanza el bot automáticamente.
    Se pausa durante el horario nocturno en España para evitar actividad sospechosa.
    """

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_check: Optional[datetime] = None
        self._last_points: Optional[int] = None
        self._next_check: Optional[datetime] = None
        self._status: str = "detenido"
        self._checks_count: int = 0
        self._autoruns_count: int = 0

        # Cargar configuración persistida
        cfg = _load_config()
        self.enabled: bool = cfg["enabled"]
        self.min_interval: int = cfg["min_interval"]
        self.max_interval: int = cfg["max_interval"]
        self.night_start: int = cfg["night_start"]
        self.night_end: int = cfg["night_end"]
        self.autorun_enabled: bool = cfg["autorun_enabled"]
        self.autorun_min_points: int = cfg["autorun_min_points"]

    # ── Propiedades públicas ────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def get_status(self) -> dict:
        """Devuelve el estado completo del chequeador para la UI."""
        return {
            "enabled": self.enabled,
            "running": self.is_running,
            "status": self._status,
            "last_check": self._last_check.strftime("%H:%M:%S") if self._last_check else None,
            "last_check_iso": self._last_check.isoformat() if self._last_check else None,
            "last_points": self._last_points,
            "next_check": self._next_check.strftime("%H:%M:%S") if self._next_check else None,
            "next_check_iso": self._next_check.isoformat() if self._next_check else None,
            "min_interval": self.min_interval,
            "max_interval": self.max_interval,
            "night_start": self.night_start,
            "night_end": self.night_end,
            "autorun_enabled": self.autorun_enabled,
            "autorun_min_points": self.autorun_min_points,
            "checks_count": self._checks_count,
            "autoruns_count": self._autoruns_count,
        }

    # ── Control de ciclo de vida ────────────────────────────────────

    def start(self):
        """Inicia el hilo de chequeo periódico."""
        if self.is_running:
            logger.info("[AUTOCHECKER] Ya está en ejecución, ignorando solicitud de inicio")
            return
        self.enabled = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="points-checker")
        self._thread.start()
        self._persist()
        logger.info("[AUTOCHECKER] ✅ Chequeador automático de puntos INICIADO")

    def stop(self):
        """Detiene el hilo de chequeo periódico."""
        self.enabled = False
        self._stop_event.set()
        self._status = "detenido"
        self._next_check = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self._persist()
        logger.info("[AUTOCHECKER] ⏹ Chequeador automático de puntos DETENIDO")

    def update_config(self, **kwargs):
        """Actualiza la configuración del chequeador y la persiste."""
        mensajes = []
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
                if key == "autorun_enabled":
                    estado = "Activada" if value else "Desactivada"
                    mensajes.append(f"Auto-ejecución: {estado}")
                elif key == "autorun_min_points":
                    mensajes.append(f"Umbral: {value} P")
                elif key in ("min_interval", "max_interval"):
                    mensajes.append(f"Intervalo {key}: {value} min")
                else:
                    mensajes.append(f"{key}: {value}")
        self._persist()
        if mensajes:
            logger.info("⚙️ [AUTOCHECKER] " + " | ".join(mensajes))

    def _persist(self):
        """Guarda la configuración actual en disco."""
        cfg = {
            "enabled": self.enabled,
            "min_interval": self.min_interval,
            "max_interval": self.max_interval,
            "night_start": self.night_start,
            "night_end": self.night_end,
            "autorun_enabled": self.autorun_enabled,
            "autorun_min_points": self.autorun_min_points,
        }
        _save_config(cfg)

    # ── Lógica de horario nocturno y cálculo de próximas ejecuciones ───

    def _get_spain_hour(self) -> int:
        """Obtiene la hora actual en España (Europe/Madrid)."""
        try:
            from zoneinfo import ZoneInfo
            now_spain = datetime.now(ZoneInfo("Europe/Madrid"))
            return now_spain.hour
        except Exception:
            # Fallback: UTC+2 (CEST, horario de verano habitual en España)
            now_utc = datetime.now(timezone.utc)
            now_spain_approx = now_utc + timedelta(hours=2)
            return now_spain_approx.hour

    def _is_hour_in_night_time(self, hora: int) -> bool:
        """Comprueba si una hora dada (0-23) cae dentro del horario de pausa."""
        if self.night_start < self.night_end:
            return self.night_start <= hora < self.night_end
        else:  # Cruce de medianoche (ej. 23:00 - 08:00)
            return hora >= self.night_start or hora < self.night_end

    def _is_night_time(self) -> bool:
        """Comprueba si es horario nocturno en España actualmente."""
        return self._is_hour_in_night_time(self._get_spain_hour())

    def calcular_proximo_chequeo(self) -> tuple[datetime, float, bool]:
        """Calcula el próximo chequeo teniendo en cuenta el horario de pausa nocturna y el jitter.
        
        Si el próximo chequeo cae dentro del horario de pausa o ya estamos en él,
        se programa para después del fin de la pausa sumando el jitter correspondiente.
        Devuelve (fecha_proximo_chequeo, segundos_de_espera, es_tras_pausa).
        """
        now = datetime.now()
        jitter_minutes = random.uniform(self.min_interval, self.max_interval)
        candidato = now + timedelta(minutes=jitter_minutes)

        tras_pausa = False
        if self._is_night_time() or self._is_hour_in_night_time(candidato.hour):
            tras_pausa = True
            fin_pausa = now.replace(hour=self.night_end, minute=0, second=0, microsecond=0)
            if now.hour >= self.night_end:
                fin_pausa += timedelta(days=1)
            # El jitter se aplica estrictamente tras el fin de la pausa
            proximo = fin_pausa + timedelta(minutes=jitter_minutes)
        else:
            proximo = candidato

        segundos_espera = max(5.0, (proximo - now).total_seconds())
        return proximo, segundos_espera, tras_pausa

    def get_summary_text(self) -> str:
        """Genera un mensaje de estado legible para la consola web."""
        if not self.enabled:
            return "Chequeo automático: INACTIVO | Auto-ejecución: DESACTIVADA"

        estado_autorun = f"ACTIVA (>= {self.autorun_min_points} P)" if self.autorun_enabled else "DESACTIVADA"
        
        if not self._next_check:
            proximo, _, _ = self.calcular_proximo_chequeo()
            self._next_check = proximo

        hora_next = self._next_check.strftime("%H:%M")
        ahora = datetime.now()
        es_hoy = self._next_check.date() == ahora.date()
        fecha_str = "hoy" if es_hoy else self._next_check.strftime("%d/%m")

        if self._is_night_time() or self._is_hour_in_night_time(self._next_check.hour):
            detalle_pausa = f"{hora_next} ({fecha_str}, tras pausa nocturna {self.night_start}:00-{self.night_end}:00 h + jitter)"
        else:
            min_faltan = max(1, int((self._next_check - ahora).total_seconds() // 60))
            detalle_pausa = f"{hora_next} (en ~{min_faltan} min, jitter {self.min_interval}-{self.max_interval} min)"

        return f"Chequeo automático: ACTIVO | Auto-ejecución: {estado_autorun} | Próximo chequeo: {detalle_pausa}"

    # ── Bucle principal ─────────────────────────────────────────────

    def _loop(self):
        """Bucle principal del chequeador en hilo de background."""
        logger.info("[AUTOCHECKER] Hilo de chequeo arrancado")

        while not self._stop_event.is_set():
            # Si estamos en pausa nocturna, programar para después de la pausa
            if self._is_night_time():
                proximo, segundos_espera, _ = self.calcular_proximo_chequeo()
                self._next_check = proximo
                hora_str = proximo.strftime("%H:%M:%S")
                self._status = f"💤 pausado (noche). Próxima ejecución: {hora_str} (tras pausa + jitter)"
                logger.info(f"[AUTOCHECKER] Pausa nocturna en curso. Próximo chequeo tras fin de pausa: {hora_str}")
                self._stop_event.wait(segundos_espera)
                if self._stop_event.is_set():
                    break

            # Ejecutar chequeo
            self._status = "🔍 chequeando puntos..."
            self._check_points()

            if self._stop_event.is_set():
                break

            # Calcular siguiente intervalo respetando pausa y jitter
            proximo, segundos_espera, tras_pausa = self.calcular_proximo_chequeo()
            self._next_check = proximo
            hora_str = proximo.strftime("%H:%M:%S")
            if tras_pausa:
                self._status = f"💤 pausa nocturna. Próximo chequeo: {hora_str} (tras pausa + jitter)"
                logger.info(f"[AUTOCHECKER] Siguiente chequeo programado tras fin de pausa nocturna: {hora_str}")
            else:
                minutos_aprox = int(segundos_espera // 60)
                self._status = f"⏳ esperando ~{minutos_aprox} min"
                logger.info(f"[AUTOCHECKER] Próximo chequeo en ~{minutos_aprox} min (a las {hora_str})")

            self._stop_event.wait(segundos_espera)

        self._status = "detenido"
        logger.info("[AUTOCHECKER] Hilo de chequeo finalizado")

    def _check_points(self):
        """Consulta los puntos actuales en SteamGifts."""
        from app.core.config import settings

        try:
            if not settings.STEAMGIFTS_PHPSESSID:
                self._status = "⚠️ error: cookie no configurada"
                logger.warning("[AUTOCHECKER] No se puede chequear: PHPSESSID no configurada")
                return

            from app.services.steamgifts_client import SteamGiftsClient

            client = SteamGiftsClient(
                phpsessid=settings.STEAMGIFTS_PHPSESSID,
                base_url=settings.STEAMGIFTS_BASE_URL,
                user_agent=settings.USER_AGENT,
                timeout=settings.HTTP_TIMEOUT_SECONDS,
            )

            if not client.is_session_valid():
                self._status = "⚠️ error: sesión inválida"
                logger.warning("[AUTOCHECKER] Sesión inválida al chequear puntos")
                return

            acc = client.get_account_info(force=True)
            self._last_points = acc.points
            self._last_check = datetime.now()
            self._checks_count += 1

            logger.info(
                f"[AUTOCHECKER] ✅ Chequeo #{self._checks_count}: "
                f"{acc.points} P (usuario: {acc.username})"
            )

            # Comprobar alerta Telegram
            if acc.points >= settings.TELEGRAM_POINTS_THRESHOLD:
                from app.services.telegram_alert import notify_points_threshold_exceeded
                notify_points_threshold_exceeded(acc.points, acc.username)

            # Autorun: si los puntos superan el mínimo configurado
            if self.autorun_enabled and acc.points >= self.autorun_min_points:
                import app.main as main_app

                if not getattr(main_app, "is_bot_running", False):
                    logger.info(
                        f"[AUTOCHECKER] 🚀 Puntos ({acc.points}) >= {self.autorun_min_points}. "
                        f"¡Lanzando ejecución automática!"
                    )
                    self._trigger_bot_run()
                    self._autoruns_count += 1
                else:
                    logger.info(
                        f"[AUTOCHECKER] Puntos suficientes ({acc.points}) "
                        f"pero el bot ya está en ejecución, omitiendo autorun"
                    )

        except Exception as e:
            self._status = f"⚠️ error: {str(e)[:80]}"
            logger.error(f"[AUTOCHECKER] Error al chequear puntos: {e}")

    def _trigger_bot_run(self):
        """Lanza una ejecución automática del bot en un hilo separado (la alerta se enviará al finalizar)."""
        from app.api.v1.bot import _ejecutar_bot_en_segundo_plano
        from app.core.logging_buffer import console_handler

        # Limpiar la consola antes de la nueva ejecución automática
        console_handler.clear()
        logger.info("[AUTOCHECKER] Consola limpiada. Iniciando ejecución automática del bot (trigger_type=auto)...")

        thread = threading.Thread(
            target=_ejecutar_bot_en_segundo_plano,
            kwargs={"trigger_type": "auto"},
            daemon=True,
            name="autorun-bot",
        )
        thread.start()

    # ── Auto-arranque al iniciar la app ─────────────────────────────

    def auto_start_if_enabled(self):
        """Arranca automáticamente si estaba habilitado en la última sesión."""
        if self.enabled and not self.is_running:
            logger.info("[AUTOCHECKER] Configuración previa detectada con autochecker activo, arrancando...")
            self.start()


# ── Instancia global (singleton) ────────────────────────────────────
points_checker = PointsChecker()

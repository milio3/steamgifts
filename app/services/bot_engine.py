"""Motor principal del bot que orquesta el escaneo y entrada en giveaways."""

import logging
import random
import time
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entry import Entry, RunLog
from app.schemas.giveaway import EntryResult, RunSummary
from app.services.steamgifts_client import SteamGiftsClient

from app.core.categories import (
    AVAILABLE_CATEGORIES,
    DEFAULT_CATEGORY_ORDER,
    load_categories_config,
)
from app.services.telegram_alert import notify_points_threshold_exceeded

logger = logging.getLogger(__name__)


class BotEngine:
    """Orquestador del bot: gestiona prioridades, puntos y registro de entradas."""

    # Orden de prioridad de categorías con sus URLs
    CATEGORY_PRIORITY = {k: v["url"] for k, v in AVAILABLE_CATEGORIES.items()}

    # Nombres legibles para los logs
    CATEGORY_NAMES = {k: v["label"] for k, v in AVAILABLE_CATEGORIES.items()}

    def __init__(self, client: SteamGiftsClient, db_session: Session):
        self.client = client
        self.db = db_session
        self._stop_logged = False

    def run(self, categories: Optional[List[str]] = None, trigger_type: str = "manual") -> RunSummary:
        """Ejecuta el bot completo: escanea categorías y entra en giveaways."""
        self._stop_logged = False
        modo_txt = "AUTOMÁTICA (AUTORUN)" if trigger_type == "auto" else "MANUAL"
        logger.info("═" * 60)
        logger.info(f"[INICIO] INICIANDO EJECUCIÓN DEL BOT ({modo_txt})")
        logger.info("═" * 60)

        if categories:
            cats_to_run = categories
        else:
            order, enabled = load_categories_config()
            cats_to_run = [c for c in order if c in enabled and c in self.CATEGORY_PRIORITY]

        # Crear registro de ejecución en BD
        run_log = RunLog(status="running", total_points_spent=0, trigger_type=trigger_type)
        self.db.add(run_log)
        self.db.commit()
        self.db.refresh(run_log)

        summary_entries: List[EntryResult] = []

        try:
            # Verificar sesión válida
            if not self.client.is_session_valid():
                raise Exception("Sesión inválida. Revisa la cookie PHPSESSID en el fichero .env")

            # Obtener información de la cuenta
            acc_info = self.client.get_account_info()
            run_log.initial_points = acc_info.points
            puntos_actuales = acc_info.points
            self.db.commit()

            logger.info(f"Usuario: {acc_info.username} │ Puntos: {puntos_actuales} P │ Nivel: {acc_info.level}")
            logger.info(f"Categorías: {', '.join(cats_to_run)}")

            # Comprobar alerta de Telegram si se alcanza el límite de puntos (ej. 400)
            if puntos_actuales >= settings.TELEGRAM_POINTS_THRESHOLD:
                notify_points_threshold_exceeded(puntos_actuales, acc_info.username)

            entradas_realizadas = 0

            for cat in cats_to_run:
                if cat not in self.CATEGORY_PRIORITY:
                    logger.warning(f"Categoría desconocida: {cat}, saltando")
                    continue

                if self._should_stop(entradas_realizadas, puntos_actuales):
                    break

                nombre_cat = self.CATEGORY_NAMES.get(cat, cat)
                logger.info(f"─── Categoría: {nombre_cat} ─────────────────────────────")

                url_cat = self.CATEGORY_PRIORITY[cat]
                entradas_cat = self._process_category(
                    url_cat, cat, run_log, puntos_actuales,
                    entradas_realizadas, summary_entries
                )

                entradas_realizadas += entradas_cat
                # Actualizar puntos actuales desde el último resultado
                if summary_entries and summary_entries[-1].points_remaining is not None:
                    puntos_actuales = summary_entries[-1].points_remaining

                logger.info(f"  → {entradas_cat} entrada(s) procesadas en {nombre_cat}")

                # Si ya no quedan puntos o se alcanzó el límite, no esperar ni procesar más categorías
                if self._should_stop(entradas_realizadas, puntos_actuales):
                    break

                # Delay entre categorías si no es la última y se hicieron entradas
                if cat != cats_to_run[-1] and entradas_cat > 0:
                    delay = settings.CATEGORY_DELAY_SECONDS
                    logger.info(f"Esperando {delay}s antes de la siguiente categoría...")
                    time.sleep(delay)

            # Finalizar ejecución
            run_log.status = "completed"
            run_log.final_points = puntos_actuales
            run_log.total_entries = entradas_realizadas
            run_log.finished_at = datetime.now(timezone.utc)
            self.db.commit()

            logger.info("═" * 60)
            logger.info(
                f"[OK] Ronda terminada: {entradas_realizadas} entradas realizadas "
                f"({run_log.total_points_spent} P gastados | {puntos_actuales} P restantes)"
            )
            logger.info("═" * 60)

            return RunSummary(
                run_id=run_log.id,
                started_at=run_log.started_at,
                finished_at=run_log.finished_at,
                total_entries=run_log.total_entries,
                total_points_spent=run_log.total_points_spent,
                initial_points=run_log.initial_points,
                final_points=run_log.final_points,
                status=run_log.status,
                trigger_type=run_log.trigger_type,
                entries=summary_entries,
            )

        except Exception as e:
            logger.error(f"[ERROR] Error en la ejecución del bot: {e}")
            run_log.status = "error"
            run_log.error_message = str(e)[:500]
            run_log.finished_at = datetime.now(timezone.utc)
            self.db.commit()
            raise

    def _process_category(
        self,
        category_url: str,
        category_name: str,
        run_log: RunLog,
        puntos_actuales: int,
        entradas_totales: int,
        summary_entries: List[EntryResult],
    ) -> int:
        """Procesa una categoría: escanea giveaways y entra en los disponibles."""
        entradas_cat = 0

        # Obtener giveaways de la primera página
        giveaways = self.client.get_giveaways(category_url, category_name)

        for gw in giveaways:
            if self._should_stop(entradas_totales + entradas_cat, puntos_actuales):
                break

            # Saltar giveaways en los que ya hemos entrado
            if gw.is_entered:
                continue

            # Verificar que tenemos puntos suficientes
            if puntos_actuales < gw.points_cost:
                logger.debug(
                    f"  [Saltado] {gw.game_name} ({gw.points_cost}P) - Puntos insuficientes ({puntos_actuales}P)"
                )
                continue

            # Delay aleatorio entre peticiones para parecer humano
            delay = random.uniform(settings.MIN_DELAY_SECONDS, settings.MAX_DELAY_SECONDS)
            logger.debug(f"  Esperando {delay:.1f}s...")
            time.sleep(delay)

            # Intentar entrar en el giveaway
            logger.info(
                f"[SORTEO] Entrando en: {gw.game_name} ({gw.points_cost}P) "
                f"[{gw.entries_count} participantes, {gw.copies} copia(s)]"
            )
            resultado = self.client.enter_giveaway(
                code=gw.giveaway_code,
                game_name=gw.game_name,
            )

            # Registrar en base de datos
            db_entry = Entry(
                game_name=gw.game_name,
                giveaway_code=gw.giveaway_code,
                giveaway_url=gw.giveaway_url,
                category=category_name,
                points_spent=gw.points_cost if resultado.result == "success" else 0,
                points_remaining=resultado.points_remaining,
                entries_count=gw.entries_count,
                copies=gw.copies,
                result=resultado.result,
                error_message=resultado.error_message,
                time_remaining=gw.time_remaining,
                run_id=run_log.id,
            )
            self.db.add(db_entry)
            self.db.commit()

            summary_entries.append(resultado)

            if resultado.result == "success":
                puntos_actuales = (
                    resultado.points_remaining
                    if resultado.points_remaining is not None
                    else puntos_actuales - gw.points_cost
                )
                entradas_cat += 1
                run_log.total_points_spent += gw.points_cost
                run_log.total_entries = entradas_totales + entradas_cat
                self.db.commit()

        return entradas_cat

    def _should_stop(self, current_entries: int, points: int) -> bool:
        """Determina si el bot debe detenerse."""
        if current_entries >= settings.MAX_ENTRIES_PER_RUN:
            if not self._stop_logged:
                logger.info(f"[LIMITE] Límite de entradas alcanzado ({settings.MAX_ENTRIES_PER_RUN})")
                self._stop_logged = True
            return True
        if points <= 0:
            if not self._stop_logged:
                logger.info("[FIN] Puntos agotados (0 P disponibles)")
                self._stop_logged = True
            return True
        return False

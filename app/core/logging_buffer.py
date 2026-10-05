"""Buffer de logs en memoria para la consola web en tiempo real."""

import html
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
from collections import deque
from datetime import datetime
from typing import Any, Dict, List

# Expresiones regulares precompiladas para máximo rendimiento
RE_URL = re.compile(r'https?://\S+')
RE_TRAILING_COLON = re.compile(r':\s*$')
RE_TAG_AUTOCHECKER = re.compile(r'\[AUTOCHECKER\]\s*', re.IGNORECASE)
RE_TAG_ERROR = re.compile(r'\[ERROR\]\s*', re.IGNORECASE)
RE_TAG_OK = re.compile(r'\[OK\]\s*', re.IGNORECASE)
RE_TAG_SORTEO = re.compile(r'\[SORTEO\]\s*', re.IGNORECASE)
RE_TAG_INICIO = re.compile(r'\[INICIO\]\s*', re.IGNORECASE)
RE_TAG_AVISO = re.compile(r'\[AVISO\]\s*', re.IGNORECASE)
RE_ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# Estilo común para todos los badges (ancho fijo exacto de 100px para alineación perfecta)
BADGE_STYLE = "display: inline-block; width: 100px; text-align: center; font-size: 0.72rem; font-weight: 700; border-radius: 3px; padding: 1px 0; margin-right: 8px; flex-shrink: 0;"


def format_log_to_html(entry: Dict[str, Any]) -> str:
    """Convierte una entrada de log a una línea HTML con badges de ancho fijo para alineación perfecta."""
    t = entry["time"]
    raw_msg = entry["msg"]
    # Limpiar secuencias ANSI y URLs largas
    clean_msg = RE_ANSI_ESCAPE.sub('', raw_msg)
    clean_msg = RE_URL.sub('', clean_msg).strip()
    clean_msg = RE_TRAILING_COLON.sub('', clean_msg)
    level = entry["level"]

    msg_lower = clean_msg.lower()

    if "[autochecker]" in msg_lower:
        badge_html = f'<span class="console-badge" style="{BADGE_STYLE} background:#17212b; color:#66c0f4; border:1px solid #2a475e;">CHECKER</span>'
        color_style = "color: #93c5fd;"
        clean_msg = RE_TAG_AUTOCHECKER.sub('', clean_msg)
    elif "[error]" in msg_lower or level == "ERROR":
        badge_html = f'<span class="console-badge" style="{BADGE_STYLE} background:rgba(217,83,79,0.2); color:#f87171; border:1px solid rgba(217,83,79,0.4);">ERROR</span>'
        color_style = "color: #f87171; font-weight: 600;"
        clean_msg = RE_TAG_ERROR.sub('', clean_msg)
    elif "[ok]" in msg_lower or "éxito" in msg_lower or "completad" in msg_lower:
        badge_html = f'<span class="console-badge" style="{BADGE_STYLE} background:rgba(92,126,16,0.2); color:#96b847; border:1px solid rgba(150,184,71,0.4);">ÉXITO</span>'
        color_style = "color: #4ade80;"
        clean_msg = RE_TAG_OK.sub('', clean_msg)
    elif "[sorteo]" in msg_lower or "entrando en" in msg_lower:
        badge_html = f'<span class="console-badge" style="{BADGE_STYLE} background:rgba(168,85,247,0.15); color:#c084fc; border:1px solid rgba(168,85,247,0.4);">SORTEO</span>'
        color_style = "color: #38bdf8;"
        clean_msg = RE_TAG_SORTEO.sub('', clean_msg)
    elif "[inicio]" in msg_lower or "iniciando" in msg_lower:
        badge_html = f'<span class="console-badge" style="{BADGE_STYLE} background:rgba(56,189,248,0.15); color:#60a5fa; border:1px solid rgba(56,189,248,0.4);">INICIO</span>'
        color_style = "color: #60a5fa; font-weight: 600;"
        clean_msg = RE_TAG_INICIO.sub('', clean_msg)
    elif "[aviso]" in msg_lower or level == "WARNING" or "esperando" in msg_lower:
        badge_html = f'<span class="console-badge" style="{BADGE_STYLE} background:rgba(229,169,60,0.15); color:#e5a93c; border:1px solid rgba(229,169,60,0.4);">AVISO</span>'
        color_style = "color: #fbbf24;"
        clean_msg = RE_TAG_AVISO.sub('', clean_msg)
    elif "cuenta:" in msg_lower or "puntos:" in msg_lower:
        badge_html = f'<span class="console-badge" style="{BADGE_STYLE} background:rgba(16,185,129,0.15); color:#34d399; border:1px solid rgba(16,185,129,0.4);">CUENTA</span>'
        color_style = "color: #a3e635; font-weight: 500;"
    else:
        badge_html = f'<span class="console-badge" style="{BADGE_STYLE} background:#19222e; color:#8f98a0; border:1px solid #2a475e;">SISTEMA</span>'
        color_style = "color: #c7d5e0;"

    escaped_msg = html.escape(clean_msg.strip())
    time_html = f'<span class="console-time text-nowrap font-monospace" style="display:inline-block; width:68px; color:#64748b; font-size:0.76rem; flex-shrink:0;">[{t}]</span>'

    return f'<div class="console-line">{time_html} {badge_html}<span style="{color_style}">{escaped_msg}</span></div>'


class WebConsoleHandler(logging.Handler):
    """Handler de logging que almacena en memoria los logs para mostrarlos en la consola web."""

    def __init__(self, max_records: int = 500):
        super().__init__()
        self.max_records = max_records
        self.logs: deque = deque(maxlen=max_records)

    def emit(self, record: logging.LogRecord):
        try:
            msg = record.getMessage()

            # Evitar logs ruidosos de peticiones HTTP habituales
            if (
                record.name.startswith("uvicorn")
                or "GET /partials/console-logs" in msg
                or "GET /partials/bot-status" in msg
                or "GET /partials/stats" in msg
                or "GET /partials/latest-entries" in msg
                or "GET /partials/execution-sessions" in msg
            ):
                return

            time_str = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
            self.logs.append({
                "time": time_str,
                "level": record.levelname,
                "name": record.name,
                "msg": msg,
            })
        except Exception:
            self.handleError(record)

    def get_logs(self) -> List[Dict[str, Any]]:
        return list(self.logs)

    def get_formatted_html(self) -> str:
        if not self.logs:
            return '<div class="console-line text-muted fst-italic">consola@steamgifts-bot:~$ Sistema en espera. Pulsa "Iniciar Ejecución" para comenzar.</div>'
        return "\n".join(format_log_to_html(log) for log in self.logs)

    def clear(self):
        self.logs.clear()


console_handler = WebConsoleHandler()


class CleanFileFormatter(logging.Formatter):
    """Formateador para el archivo .log que elimina secuencias de escape ANSI."""

    def format(self, record: logging.LogRecord) -> str:
        record_msg = record.getMessage()
        clean = RE_ANSI_ESCAPE.sub('', record_msg)
        orig_msg = record.msg
        orig_args = record.args
        record.msg = clean
        record.args = None
        try:
            return super().format(record)
        finally:
            record.msg = orig_msg
            record.args = orig_args


def setup_file_logging(
    log_dir: str = "logs",
    log_filename: str = "steamgifts_bot.log",
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB
    backup_count: int = 5,
) -> RotatingFileHandler:
    """Configura y añade un RotatingFileHandler al logger raíz para registrar ejecuciones y chequeos."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    file_target = log_path / log_filename

    file_handler = RotatingFileHandler(
        file_target,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    formatter = CleanFileFormatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)

    # Evitar duplicar handlers si ya está registrado
    root_logger = logging.getLogger()
    for h in root_logger.handlers:
        if isinstance(h, RotatingFileHandler) and getattr(h, 'baseFilename', None) == str(file_target.resolve()):
            return h

    root_logger.addHandler(file_handler)
    return file_handler

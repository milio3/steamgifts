"""Buffer de logs en memoria para la consola web en tiempo real."""

import html
import logging
import re
from collections import deque
from datetime import datetime
from typing import Any, Dict, List


def format_log_to_html(entry: Dict[str, Any]) -> str:
    """Convierte una entrada de log a una línea HTML estilizada sin emojis ni URLs largas para la consola."""
    t = entry["time"]
    raw_msg = entry["msg"]
    # Limpiar URLs que puedan romper el formato visual de la consola
    clean_msg = re.sub(r'https?://\S+', '', raw_msg).strip()
    clean_msg = re.sub(r':\s*$', '', clean_msg)
    escaped_msg = html.escape(clean_msg)
    level = entry["level"]

    color_class = "text-light"
    icon_svg = ""

    msg_lower = raw_msg.lower()

    if "[ok]" in msg_lower or "completad" in msg_lower or "éxito" in msg_lower:
        color_class = "text-success fw-medium"
        icon_svg = '<svg class="tailwind-svg-mini text-success me-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5" /></svg>'
    elif "[error]" in msg_lower or level == "ERROR":
        color_class = "text-danger fw-bold"
        icon_svg = '<svg class="tailwind-svg-mini text-danger me-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" /></svg>'
    elif "[aviso]" in msg_lower or level == "WARNING":
        color_class = "text-warning fw-medium"
        icon_svg = '<svg class="tailwind-svg-mini text-warning me-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" /></svg>'
    elif "[sorteo]" in msg_lower or "entrando en" in msg_lower:
        color_class = "text-info fw-medium"
        icon_svg = '<svg class="tailwind-svg-mini text-info me-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.347a1.125 1.125 0 0 1 0 1.972l-11.54 6.347a1.125 1.125 0 0 1-1.667-.986V5.653Z" /></svg>'
    elif "[inicio]" in msg_lower or "iniciando" in msg_lower:
        color_class = "text-primary fw-bold"
        icon_svg = '<svg class="tailwind-svg-mini text-primary me-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="m3.75 13.5 10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75Z" /></svg>'
    elif "═" in raw_msg or "───" in raw_msg:
        color_class = "text-secondary small"
    elif "esperando" in msg_lower:
        color_class = "text-warning"
    elif "[limite]" in msg_lower or "[fin]" in msg_lower:
        color_class = "text-warning fw-bold"
        icon_svg = '<svg class="tailwind-svg-mini text-warning me-1" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 5.25v13.5m-7.5-13.5v13.5" /></svg>'

    return f'<div class="console-line"><span class="console-time text-muted">[{t}]</span> {icon_svg}<span class="{color_class}">{escaped_msg}</span></div>'


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

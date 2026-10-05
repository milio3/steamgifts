"""Script de línea de comandos (CLI) para ejecución manual, diagnóstico y estadísticas de SteamGifts Bot."""

import argparse
import csv
import logging
import os
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

# Asegurar codificación UTF-8 y compatibilidad ANSI en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        os.system("")  # Habilita secuencias ANSI en cmd y PowerShell
    except Exception:
        pass

# Estilos y colores ANSI
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[90m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_WHITE = "\033[97m"
C_RED = "\033[91m"


class ConsoleFormatter(logging.Formatter):
    """Formateador limpio y elegante para terminales modernas."""

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()

        # Si es un separador decorativo, mostrarlo sutil sin timestamp
        if msg.startswith(("─", "═", "━", "┌", "└", "├")):
            return f"{C_DIM}{msg}{C_RESET}"

        time_str = f"{C_DIM}{self.formatTime(record, '%H:%M:%S')}{C_RESET}"

        if record.levelno >= logging.ERROR:
            return f"{time_str} │ {C_RED}❌ {msg}{C_RESET}"
        elif record.levelno >= logging.WARNING:
            return f"{time_str} │ {C_YELLOW}⚠️  {msg}{C_RESET}"

        return f"{time_str} │ {msg}"


# Configuración del Logger raíz para el CLI
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ConsoleFormatter())
logging.root.handlers = [handler]
logging.root.setLevel(logging.INFO)
logger = logging.getLogger("SteamGiftsCLI")

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.logging_buffer import setup_file_logging
from app.models.entry import Entry, RunLog
from app.services.bot_engine import BotEngine
from app.services.steamgifts_client import SteamGiftsClient

# Asegurar persistencia de logs en fichero .log
setup_file_logging()


def text_width(s: str) -> int:
    """Calcula el ancho visual de una cadena en terminal (teniendo en cuenta emojis)."""
    w = 0
    for ch in s:
        code = ord(ch)
        if (
            unicodedata.east_asian_width(ch) in ("W", "F")
            or code > 0x1F000
            or code in (0x2705, 0x274C, 0x23F3, 0x26A0, 0x2B50, 0x2714, 0x1F4E6, 0x1F465)
        ):
            w += 2
        else:
            w += 1
    return w


def print_box(title: str, items: list, width: int = 58, label_col: int = 33):
    """Imprime una caja estilizada y alineada en la consola."""
    border_c = C_CYAN
    title_c = C_BOLD + C_WHITE

    print(f"\n{border_c}┌{'─' * (width - 2)}┐{C_RESET}")
    w_title = text_width(title)
    title_pad = max(0, (width - 4 - w_title) // 2)
    right_pad = max(0, width - 4 - w_title - title_pad)
    print(f"{border_c}│{C_RESET} {' ' * title_pad}{title_c}{title}{C_RESET}{' ' * right_pad} {border_c}│{C_RESET}")
    print(f"{border_c}├{'─' * (width - 2)}┤{C_RESET}")

    for item in items:
        if len(item) == 1:
            sub = item[0]
            w_sub = text_width(sub)
            pad = max(0, width - 6 - w_sub)
            print(f"{border_c}│{C_RESET}  {C_BOLD}{sub}{C_RESET}{' ' * pad}  {border_c}│{C_RESET}")
        else:
            label, val, color = item
            val_colored = f"{color}{val}{C_RESET}" if color else str(val)
            w_label = text_width(label)
            w_val = text_width(str(val))
            label_pad = max(1, label_col - w_label)
            val_pad = max(0, width - 2 - 2 - w_label - label_pad - 2 - w_val - 2)
            print(f"{border_c}│{C_RESET}  {C_WHITE}{label}{C_RESET}{' ' * label_pad}: {val_colored}{' ' * val_pad}  {border_c}│{C_RESET}")

    print(f"{border_c}└{'─' * (width - 2)}┘{C_RESET}\n")


def asegurar_base_de_datos():
    """Asegura que el directorio data y las tablas SQLite existan."""
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=engine)


def verificar_sesion():
    """Verifica la validez de la cookie PHPSESSID y muestra los datos de la cuenta."""
    if not settings.STEAMGIFTS_PHPSESSID:
        print(f"\n{C_RED}❌ Error: La variable STEAMGIFTS_PHPSESSID está vacía en el fichero .env.{C_RESET}")
        print("   Configura tu cookie de sesión antes de continuar.\n")
        sys.exit(1)

    print(f"\n{C_CYAN}🔍 Verificando conexión con SteamGifts...{C_RESET}")
    client = SteamGiftsClient(
        phpsessid=settings.STEAMGIFTS_PHPSESSID,
        base_url=settings.STEAMGIFTS_BASE_URL,
        user_agent=settings.USER_AGENT,
        timeout=settings.HTTP_TIMEOUT_SECONDS,
    )

    if not client.is_session_valid():
        print(f"{C_RED}❌ Error: No se pudo validar la sesión.{C_RESET}")
        print("   Posibles causas:")
        print("   - La cookie PHPSESSID ha expirado.")
        print("   - Cloudflare requiere resolver una comprobación en el navegador.\n")
        sys.exit(1)

    try:
        acc = client.get_account_info()
        items = [
            ("Usuario", acc.username, C_GREEN),
            ("Puntos actuales", f"{acc.points} / 400 P", C_YELLOW),
            ("Nivel de cuenta", f"Nivel {acc.level}", C_CYAN),
            ("Token XSRF", "Válido (OK)" if acc.xsrf_token else "No detectado", C_GREEN if acc.xsrf_token else C_RED),
        ]
        print_box("🎮 ESTADO DE CUENTA STEAMGIFTS", items)
    except Exception as e:
        print(f"{C_RED}❌ Error al consultar los datos: {e}{C_RESET}\n")
        sys.exit(1)


def mostrar_estadisticas():
    """Muestra estadísticas resumidas de todas las entradas registradas."""
    asegurar_base_de_datos()
    db = SessionLocal()
    try:
        total = db.query(Entry).count()
        exitosas = db.query(Entry).filter(Entry.result == "success").count()
        errores = db.query(Entry).filter(Entry.result == "error").count()
        puntos = db.query(Entry.points_spent).filter(Entry.result == "success").all()
        total_puntos = sum(p[0] for p in puntos)
        total_runs = db.query(RunLog).count()

        items = [
            ("Total participaciones intentadas", str(total), C_WHITE),
            ("Entradas exitosas", str(exitosas), C_GREEN),
            ("Errores / Fallidas", str(errores), C_RED if errores > 0 else C_WHITE),
            ("Puntos totales invertidos", f"{total_puntos} P", C_YELLOW),
            ("Rondas de ejecución realizadas", str(total_runs), C_CYAN),
        ]

        from sqlalchemy import func
        por_cat = (
            db.query(Entry.category, func.count(Entry.id))
            .filter(Entry.result == "success")
            .group_by(Entry.category)
            .all()
        )
        if por_cat:
            items.append(("Distribución por categoría (exitosas):",))
            for cat, count in por_cat:
                nombre = BotEngine.CATEGORY_NAMES.get(cat, cat)
                items.append((f"  • {nombre}", str(count), C_CYAN))

        print_box("📊 ESTADÍSTICAS GLOBALES DEL BOT", items)
    finally:
        db.close()


def exportar_csv(archivo_salida: str):
    """Exporta todas las entradas almacenadas a un archivo CSV."""
    asegurar_base_de_datos()
    db = SessionLocal()
    try:
        entries = db.query(Entry).order_by(Entry.timestamp.desc()).all()
        if not entries:
            print(f"{C_YELLOW}⚠️ No hay entradas para exportar.{C_RESET}")
            return

        with open(archivo_salida, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "ID", "Fecha_Hora", "Juego", "Codigo_Sorteo", "URL_Sorteo",
                "Categoria", "Puntos_Gastados", "Puntos_Restantes", "Participantes",
                "Copias", "Resultado", "Mensaje_Error", "ID_Ejecucion"
            ])
            for e in entries:
                writer.writerow([
                    e.id,
                    e.timestamp.isoformat() if e.timestamp else "",
                    e.game_name,
                    e.giveaway_code,
                    e.giveaway_url,
                    e.category,
                    e.points_spent,
                    e.points_remaining,
                    e.entries_count,
                    e.copies,
                    e.result,
                    e.error_message or "",
                    e.run_id or ""
                ])

        print(f"{C_GREEN}✅ Se exportaron {len(entries)} registros a '{archivo_salida}'{C_RESET}")
    finally:
        db.close()


def ejecutar_bot(categories=None, max_entries=None):
    """Ejecuta una ronda del bot por consola."""
    asegurar_base_de_datos()

    if not settings.STEAMGIFTS_PHPSESSID:
        print(f"\n{C_RED}❌ Error: La variable STEAMGIFTS_PHPSESSID está vacía en el fichero .env.{C_RESET}")
        print("   Configura tu cookie de sesión antes de continuar.\n")
        sys.exit(1)

    if max_entries:
        settings.MAX_ENTRIES_PER_RUN = max_entries

    if categories:
        categories = ["multiple_copies" if c in ("Multiple Copies", "multiple_copies", "multiple copies") else c for c in categories]

    db = SessionLocal()
    try:
        client = SteamGiftsClient(
            phpsessid=settings.STEAMGIFTS_PHPSESSID,
            base_url=settings.STEAMGIFTS_BASE_URL,
            user_agent=settings.USER_AGENT,
            timeout=settings.HTTP_TIMEOUT_SECONDS,
        )
        engine_bot = BotEngine(client=client, db_session=db)
        summary = engine_bot.run(categories=categories)

        estado_color = C_GREEN if summary.status == "completed" else C_RED
        items = [
            ("Identificador de ronda", f"#{summary.run_id}", C_CYAN),
            ("Estado final", summary.status, estado_color),
            ("Entradas realizadas", str(summary.total_entries), C_GREEN),
            ("Puntos gastados", f"{summary.total_points_spent} P", C_YELLOW),
            ("Puntos (inicio → fin)", f"{summary.initial_points} P → {summary.final_points} P", C_WHITE),
        ]
        print_box("🏁 RESUMEN FINAL DE LA EJECUCIÓN", items)

    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}⚠️ Ejecución interrumpida por el usuario.{C_RESET}\n")
    except Exception as e:
        print(f"\n{C_RED}❌ Error durante la ejecución: {e}{C_RESET}\n")
        sys.exit(1)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="SteamGifts Bot - Cliente CLI para automatización y estadísticas",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verifica la sesión y muestra los puntos y nivel actuales sin participar en sorteos.",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Muestra las estadísticas históricas de participaciones.",
    )
    parser.add_argument(
        "--export-csv",
        type=str,
        metavar="FICHERO",
        help="Exporta todo el historial de participaciones a un archivo CSV (ej. entradas.csv).",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=["wishlist", "dlc", "group", "multiple_copies", "recommended", "new", "all"],
        help="Categorías específicas a procesar y su orden de prioridad.\n"
             "Opciones: wishlist, dlc, group, multiple_copies, recommended, new, all",
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        metavar="N",
        help="Número máximo de sorteos en los que entrar durante esta ronda.",
    )

    args = parser.parse_args()

    if args.check:
        verificar_sesion()
    elif args.stats:
        mostrar_estadisticas()
    elif args.export_csv:
        exportar_csv(args.export_csv)
    else:
        ejecutar_bot(categories=args.categories, max_entries=args.max_entries)


if __name__ == "__main__":
    main()

"""Script de línea de comandos (CLI) para ejecución manual, diagnóstico y estadísticas de SteamGifts Bot."""

import argparse
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path

# Asegurar codificación UTF-8 en Windows para emojis y caracteres acentuados
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Configurar logging para el CLI
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("SteamGiftsCLI")

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.models.entry import Entry, RunLog
from app.services.bot_engine import BotEngine
from app.services.steamgifts_client import SteamGiftsClient


def asegurar_base_de_datos():
    """Asegura que el directorio data y las tablas SQLite existan."""
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=engine)


def verificar_sesion():
    """Verifica la validez de la cookie PHPSESSID y muestra los datos de la cuenta."""
    if not settings.STEAMGIFTS_PHPSESSID:
        print("\n❌ Error: La variable STEAMGIFTS_PHPSESSID está vacía en el fichero .env.")
        print("   Configura tu cookie de sesión antes de continuar.\n")
        sys.exit(1)

    print("\n🔍 Verificando conexión con SteamGifts...")
    client = SteamGiftsClient(
        phpsessid=settings.STEAMGIFTS_PHPSESSID,
        base_url=settings.STEAMGIFTS_BASE_URL,
        user_agent=settings.USER_AGENT,
        timeout=settings.HTTP_TIMEOUT_SECONDS,
    )

    if not client.is_session_valid():
        print("❌ Error: No se pudo validar la sesión.")
        print("   Posibles causas:")
        print("   - La cookie PHPSESSID ha expirado.")
        print("   - Cloudflare requiere resolver una comprobación en el navegador.")
        sys.exit(1)

    try:
        acc = client.get_account_info()
        print("\n" + "=" * 45)
        print("   🎮 ESTADO DE CUENTA STEAMGIFTS")
        print("=" * 45)
        print(f"   👤 Usuario:           {acc.username}")
        print(f"   💰 Puntos actuales:   {acc.points} / 400 P")
        print(f"   ⭐ Nivel de cuenta:   Nivel {acc.level}")
        print(f"   🛡️ Token XSRF:        {'OK' if acc.xsrf_token else 'No detectado'}")
        print("=" * 45 + "\n")
    except Exception as e:
        print(f"❌ Error al consultar los datos: {e}\n")
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

        print("\n" + "=" * 50)
        print("   📊 ESTADÍSTICAS GLOBALES DEL BOT")
        print("=" * 50)
        print(f"   Total de participaciones intentadas: {total}")
        print(f"   ✅ Exitosas:                         {exitosas}")
        print(f"   ❌ Errores:                          {errores}")
        print(f"   💰 Puntos totales invertidos:        {total_puntos} P")
        print(f"   🚀 Rondas de ejecución realizadas:   {total_runs}")

        # Por categoría
        from sqlalchemy import func
        por_cat = (
            db.query(Entry.category, func.count(Entry.id))
            .filter(Entry.result == "success")
            .group_by(Entry.category)
            .all()
        )
        if por_cat:
            print("\n   Distribución por categoría (exitosas):")
            for cat, count in por_cat:
                nombre = BotEngine.CATEGORY_NAMES.get(cat, cat)
                print(f"     • {nombre:<25}: {count}")

        print("=" * 50 + "\n")
    finally:
        db.close()


def exportar_csv(archivo_salida: str):
    """Exporta todas las entradas almacenadas a un archivo CSV."""
    asegurar_base_de_datos()
    db = SessionLocal()
    try:
        entries = db.query(Entry).order_by(Entry.timestamp.desc()).all()
        if not entries:
            print("⚠️ No hay entradas para exportar.")
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

        print(f"✅ Se exportaron {len(entries)} registros a '{archivo_salida}'")
    finally:
        db.close()


def ejecutar_bot(categories=None, max_entries=None):
    """Ejecuta una ronda del bot por consola."""
    asegurar_base_de_datos()

    if not settings.STEAMGIFTS_PHPSESSID:
        print("\n❌ Error: La variable STEAMGIFTS_PHPSESSID está vacía en el fichero .env.")
        print("   Configura tu cookie de sesión antes de continuar.\n")
        sys.exit(1)

    if max_entries:
        settings.MAX_ENTRIES_PER_RUN = max_entries

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

        print("\n" + "=" * 55)
        print("   🏁 RESUMEN FINAL DE LA EJECUCIÓN")
        print("=" * 55)
        print(f"   Identificador de ejecución:  #{summary.run_id}")
        print(f"   Estado final:                {summary.status}")
        print(f"   Entradas realizadas:         {summary.total_entries}")
        print(f"   Puntos gastados:             {summary.total_points_spent} P")
        print(f"   Puntos iniciales / finales:  {summary.initial_points} P → {summary.final_points} P")
        print("=" * 55 + "\n")

    except KeyboardInterrupt:
        print("\n⚠️ Ejecución interrumpida por el usuario.\n")
    except Exception as e:
        print(f"\n❌ Error durante la ejecución: {e}\n")
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
        choices=["wishlist", "dlc", "group", "multiple_copies", "new"],
        help="Categorías específicas a procesar y su orden de prioridad.\n"
             "Opciones disponibles: wishlist, dlc, group, multiple_copies, new",
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

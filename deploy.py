#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de despliegue automatizado y diagnóstico para SteamGifts Bot en Raspberry Pi (DietPi) vía SSH.
Conforme a las convenciones de GEMINI.md.

Uso:
    python deploy.py                   # Despliegue completo con pull, build y arranque
    python deploy.py --logs            # Ver logs en vivo del contenedor Docker
    python deploy.py --check           # Diagnóstico del contenedor, archivos y endpoints
    python deploy.py --sync-db         # Desplegar forzando subida de la BD local
    python deploy.py --cmd "uptime"    # Ejecutar comando administrativo remoto
"""

import argparse
import getpass
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

try:
    import paramiko
except ImportError:
    print("[ERROR] La librería 'paramiko' no está instalada. Instálala con: pip install paramiko")
    sys.exit(1)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent
APP_NAME = "steamgifts"
PORT_SERVICE = 8090
DEFAULT_HOST = "192.168.1.33"
DEFAULT_USER = "dev"


def conectar_ssh(host: str, user: str, password: str = None):
    """Establece conexión SSH con la Raspberry Pi."""
    if not password:
        password = os.environ.get("RPI_PASSWORD")
    if not password:
        password = getpass.getpass(f"Introduce la contraseña SSH para {user}@{host}: ")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username=user, password=password, timeout=10)
    return ssh, password


def run_cmd(ssh, password, cmd, sudo=False):
    """Ejecuta un comando remoto por SSH con o sin privilegios de sudo."""
    print(f"\n---> Ejecutando: {cmd}")
    if sudo:
        escaped_cmd = cmd.replace("\\", "\\\\").replace('"', '\\"')
        full_cmd = f'echo "{password}" | sudo -S bash -c "{escaped_cmd}"'
    else:
        full_cmd = cmd
    stdin, stdout, stderr = ssh.exec_command(full_cmd)
    out = stdout.read().decode("utf-8", errors="ignore")
    err = stderr.read().decode("utf-8", errors="ignore")
    if out:
        print("[OUT]", out.strip())
    if err and "password for dev:" not in err and "[sudo]" not in err:
        print("[ERR]", err.strip())
    return out, err


def diagnostico_remoto(ssh, password, host):
    """Ejecuta un diagnóstico completo del contenedor, procesos y salud."""
    print("\n" + "=" * 60)
    print(f"🔍 DIAGNÓSTICO REMOTO — SteamGifts Bot ({host})")
    print("=" * 60)

    # 1. Estado de Docker
    run_cmd(ssh, password, "docker ps -a --filter name=steamgifts", sudo=True)

    # 2. Puertos a la escucha
    run_cmd(ssh, password, f"ss -tulpn | grep :{PORT_SERVICE} || echo 'Puerto {PORT_SERVICE} no ocupado'", sudo=True)

    # 3. Comprobación de salud HTTP
    print(f"\n---> Comprobando endpoint de salud HTTP en http://{host}:{PORT_SERVICE}/health...")
    health_url = f"http://{host}:{PORT_SERVICE}/health"
    try:
        with urllib.request.urlopen(health_url, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"✅ Respuesta de salud OK: {data}")
    except Exception as e:
        print(f"⚠️ Aviso de salud: {e}")


def ver_logs(ssh, password):
    """Muestra los logs del contenedor en tiempo real."""
    print(f"\n---> Mostrando logs en vivo del contenedor 'steamgifts-bot' (Ctrl+C para salir)...")
    cmd = "docker logs -f --tail 100 steamgifts-bot"
    escaped_cmd = cmd.replace("\\", "\\\\").replace('"', '\\"')
    full_cmd = f'echo "{password}" | sudo -S bash -c "{escaped_cmd}"'
    stdin, stdout, stderr = ssh.exec_command(full_cmd, get_pty=True)
    try:
        for line in iter(stdout.readline, ""):
            if line:
                print(line, end="")
    except KeyboardInterrupt:
        print("\nLectura de logs finalizada.")


def deploy(sync_database: bool = False, host: str = None, user: str = None, password: str = None):
    """Ejecuta el ciclo completo de despliegue a producción."""
    if not host:
        host = os.environ.get("RPI_HOST", DEFAULT_HOST)
    if not user:
        user = os.environ.get("RPI_USER", DEFAULT_USER)

    print("\n" + "=" * 60)
    print(f"🚀 DESPLIEGUE A PRODUCCIÓN — SteamGifts Bot en {host}")
    print("=" * 60)

    ssh, password = conectar_ssh(host, user, password)

    try:
        # 1. Crear directorios estándar y asignar permisos
        run_cmd(ssh, password, "mkdir -p /opt/apps", sudo=True)
        run_cmd(ssh, password, f"mkdir -p /mnt/dietpi_userdata/apps/{APP_NAME}/data", sudo=True)
        run_cmd(ssh, password, f"mkdir -p /opt/apps/{APP_NAME}/data", sudo=True)
        run_cmd(ssh, password, f"chown -R dev:dev /mnt/dietpi_userdata/apps/{APP_NAME}", sudo=True)
        run_cmd(ssh, password, f"chmod -R 777 /mnt/dietpi_userdata/apps/{APP_NAME}", sudo=True)
        run_cmd(ssh, password, "chown -R dev:dev /opt/apps", sudo=True)

        # 2. Clonar o sincronizar repositorio con git master
        check_dir, _ = run_cmd(ssh, password, f"test -d /opt/apps/{APP_NAME} && echo 'EXISTE' || echo 'NO_EXISTE'")
        if "EXISTE" in check_dir:
            print("El repositorio ya existe. Sincronizando con origin/master...")
            run_cmd(ssh, password, f"chown -R dev:dev /opt/apps/{APP_NAME}", sudo=True)
            run_cmd(ssh, password, f"git config --global --add safe.directory /opt/apps/{APP_NAME}")
            run_cmd(ssh, password, f"cd /opt/apps/{APP_NAME} && git fetch --all && git checkout master && git reset --hard origin/master")
        else:
            print("Clonando repositorio (rama master)...")
            run_cmd(ssh, password, f"git clone -b master https://github.com/milio3/{APP_NAME}.git /opt/apps/{APP_NAME}")
            run_cmd(ssh, password, f"chown -R dev:dev /opt/apps/{APP_NAME}", sudo=True)

        # 3. Configuración .env
        run_cmd(ssh, password, f"test -f /opt/apps/{APP_NAME}/.env || cp /opt/apps/{APP_NAME}/.env.example /opt/apps/{APP_NAME}/.env")
        run_cmd(ssh, password, f"chmod 666 /opt/apps/{APP_NAME}/.env", sudo=True)

        # 4. Sincronizar base de datos local si se solicita
        if sync_database:
            local_db = PROJECT_ROOT / "data" / "database.db"
            run_cmd(ssh, password, f"rm -f /mnt/dietpi_userdata/apps/{APP_NAME}/data/database.db-wal /mnt/dietpi_userdata/apps/{APP_NAME}/data/database.db-shm", sudo=True)
            run_cmd(ssh, password, f"rm -f /opt/apps/{APP_NAME}/data/database.db-wal /opt/apps/{APP_NAME}/data/database.db-shm", sudo=True)
            run_cmd(ssh, password, f"chown -R dev:dev /mnt/dietpi_userdata/apps/{APP_NAME}/data", sudo=True)
            run_cmd(ssh, password, f"chmod -R 777 /mnt/dietpi_userdata/apps/{APP_NAME}/data", sudo=True)

            sftp = ssh.open_sftp()
            if local_db.exists():
                print(f"\n---> Subiendo base de datos actualizada ({local_db})...")
                sftp.put(str(local_db), f"/mnt/dietpi_userdata/apps/{APP_NAME}/data/database.db")
                try:
                    sftp.put(str(local_db), f"/opt/apps/{APP_NAME}/data/database.db")
                except Exception:
                    pass
            sftp.close()

        # 5. Reconstrucción y arranque de contenedores Docker
        print("\n---> Reconstruyendo e iniciando servicios con Docker Compose...")
        run_cmd(ssh, password, f"cd /opt/apps/{APP_NAME} && (docker compose down || docker-compose down)", sudo=True)
        run_cmd(ssh, password, f"cd /opt/apps/{APP_NAME} && (docker compose build --no-cache || docker-compose build --no-cache)", sudo=True)
        run_cmd(ssh, password, f"cd /opt/apps/{APP_NAME} && (docker compose up -d || docker-compose up -d)", sudo=True)

        # 6. Comprobación de salud tras el despliegue
        print("\n---> Esperando arranque del contenedor para verificar salud...")
        time.sleep(5)
        health_url = f"http://{host}:{PORT_SERVICE}/health"
        try:
            with urllib.request.urlopen(health_url, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "ok":
                    print(f"✅ ¡Despliegue verificado con éxito en la Raspberry Pi! Versión activa: {data.get('version')}")
        except Exception as e:
            print(f"Aviso al verificar endpoint de salud ({health_url}): {e}")

        print("\n" + "=" * 60)
        print("✅ Despliegue de SteamGifts completado")
        print(f"🌐 Panel web disponible en: http://{host}:{PORT_SERVICE}")
        print("=" * 60)

    finally:
        ssh.close()


def main():
    parser = argparse.ArgumentParser(description="Herramienta de despliegue y administración remota de SteamGifts Bot.")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"IP o hostname de la Raspberry Pi (por defecto {DEFAULT_HOST})")
    parser.add_argument("--user", default=DEFAULT_USER, help=f"Usuario SSH (por defecto {DEFAULT_USER})")
    parser.add_argument("--password", default=None, help="Contraseña SSH para el usuario dev en la Raspberry Pi")
    parser.add_argument("--sync-db", action="store_true", help="Sube la base de datos SQLite local a la Raspberry Pi")
    parser.add_argument("--check", action="store_true", help="Diagnóstico remoto del estado de Docker, puertos y salud")
    parser.add_argument("--logs", action="store_true", help="Muestra los logs del contenedor Docker en tiempo real")
    parser.add_argument("--cmd", type=str, help="Ejecuta un comando administrativo personalizado en el servidor remoto")

    args = parser.parse_args()

    if args.check:
        ssh, pwd = conectar_ssh(args.host, args.user, args.password)
        try:
            diagnostico_remoto(ssh, pwd, args.host)
        finally:
            ssh.close()
    elif args.logs:
        ssh, pwd = conectar_ssh(args.host, args.user, args.password)
        try:
            ver_logs(ssh, pwd)
        finally:
            ssh.close()
    elif args.cmd:
        ssh, pwd = conectar_ssh(args.host, args.user, args.password)
        try:
            run_cmd(ssh, pwd, args.cmd, sudo=True)
        finally:
            ssh.close()
    else:
        deploy(sync_database=args.sync_db, host=args.host, user=args.user, password=args.password)


if __name__ == "__main__":
    main()

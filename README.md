# 🎮 SteamGifts Auto-Enter Bot

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL%20Mode-003B57.svg?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)

Aplicación moderna y ligera en **Python (FastAPI + HTMX)** para automatizar de forma inteligente y segura la participación en sorteos de [SteamGifts.com](https://www.steamgifts.com/), con priorización de categorías, chequeo autónomo de puntos, pausas humanas, registro persistente en SQLite y alertas en Telegram.

---

## ✨ Características Principales

- 🔄 **Chequeo Automático con Jitter:** Consulta periódica inteligente con intervalos aleatorios y pausa nocturna (España) para evitar comportamientos detectables.
- ⚡ **Auto-Ejecución Inteligente:** Lanza rondas automáticas al alcanzar el umbral de puntos deseado (ej. $\ge 380$ P).
- 🌟 **Priorización por Categorías:** Orden configurable y personalizable con drag & drop:
  1. *Wishlist (Lista de deseados)*
  2. *DLCs*
  3. *Grupos*
  4. *Múltiples copias*
  5. *Nuevos sorteos*
- 🖥️ **Panel Web en Tiempo Real:** Interfaz estilo SteamGifts Dark con consola en vivo, métricas, historial paginado y sesiones de ejecución.
- 💬 **Alertas de Telegram:** Notificaciones instantáneas al alcanzar límites de puntos y resúmenes de rondas automáticas.
- 🛡️ **Comportamiento Humano:** *Jitter* configurable entre entradas (3-8s) y pausas entre categorías para respetar rate limits y Cloudflare.
- 📝 **Registro en Fichero `.log`:** Guardado persistente y rotativo en `logs/steamgifts_bot.log`.
- 💻 **Cliente CLI:** Control total desde la terminal con `python cli.py`.

---

## 🔑 Obtención de la Cookie `PHPSESSID`

1. Inicia sesión en [SteamGifts](https://www.steamgifts.com).
2. Abre las herramientas de desarrollo (<kbd>F12</kbd>).
3. Ve a **Application** (Chrome/Edge) o **Storage** (Firefox) → **Cookies** → `https://www.steamgifts.com`.
4. Copia el valor de **`PHPSESSID`** y pégalo en tu archivo `.env`.

> ⚠️ **Aviso de seguridad:** Tu `PHPSESSID` equivale a tu sesión activa. Nunca la compartas ni la subas a repositorios públicos.

---

## ⚡ Despliegue Rápido con Docker Compose

```bash
# 1. Clonar el repositorio
git clone <url-del-repo> steamgifts && cd steamgifts

# 2. Configurar variables de entorno
cp .env.example .env
# Edita .env y añade tu STEAMGIFTS_PHPSESSID

# 3. Arrancar el contenedor
docker compose up -d --build
```

El panel web estará disponible en `http://localhost:8086` (o el puerto configurado en `.env`).

---

## 🛠️ Ejecución Local con Python

```bash
# 1. Crear y activar entorno virtual
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar .env y lanzar el servidor web
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8086 --reload
```

---

## 💻 Uso por Consola (CLI)

```bash
python cli.py --check                         # Comprobar estado de la sesión y puntos
python cli.py                                 # Ejecutar una ronda completa
python cli.py --categories wishlist dlc       # Ejecutar solo categorías específicas
python cli.py --stats                         # Ver estadísticas globales
python cli.py --export-csv historial.csv       # Exportar entradas a CSV
```

---

## ⚙️ Variables de Entorno Esenciales

| Variable | Descripción | Valor por defecto |
| :--- | :--- | :--- |
| `STEAMGIFTS_PHPSESSID` | Cookie de sesión activa de SteamGifts | `""` |
| `PORT` | Puerto del servidor web | `8086` |
| `MAX_ENTRIES_PER_RUN` | Límite de sorteos por ronda | `25` |
| `MIN_DELAY_SECONDS` | Pausa mínima entre sorteos | `3.0` |
| `MAX_DELAY_SECONDS` | Pausa máxima entre sorteos | `8.0` |
| `TELEGRAM_ALERTS_ENABLED` | Activar avisos por Telegram | `true` |
| `TELEGRAM_BOT_TOKEN` | Token de tu bot de Telegram | `""` |
| `TELEGRAM_CHAT_ID` | Tu Chat ID de Telegram | `""` |

---

## 📁 Estructura del Proyecto

```text
steamgifts/
├── app/
│   ├── api/             # Endpoints REST (/health, /api/v1/bot, /api/v1/entries)
│   ├── core/            # Configuración (.env), BD SQLite (WAL) y buffer de logs
│   ├── models/          # Modelos SQLAlchemy (Entry, RunLog con índices)
│   ├── schemas/         # Esquemas Pydantic
│   ├── services/        # Cliente HTTP, motor de sorteos, autochecker y Telegram
│   └── web/             # Rutas Jinja2, parciales HTMX, estáticos (CSS/JS)
├── cli.py               # Herramienta CLI de terminal
├── docker-compose.yml   # Despliegue con Docker Compose
├── Dockerfile           # Imagen ligera en Python 3.12
└── logs/                # Registro rotativo de ejecuciones y chequeos (.log)
```

---

## ⚖️ Licencia y Responsabilidad

Este proyecto es para fines educativos y de uso personal. Utiliza retardos aleatorios y límites razonables para interactuar de forma responsable con los servidores de SteamGifts.

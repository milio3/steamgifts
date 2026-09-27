# 🎮 SteamGifts Auto-Enter Bot

Aplicación modular en **Python / FastAPI** para automatizar la participación en sorteos de [SteamGifts.com](https://www.steamgifts.com/) con gestión inteligente de puntos, priorización estricta por categorías, persistencia completa en SQLite, interfaz web con Jinja2 + HTMX y cliente CLI para terminal.

---

## 🚀 Características Principales

- **Autenticación sin contraseñas:** Utiliza únicamente la cookie de sesión `PHPSESSID` obtenida del navegador tras el login vía Steam OpenID.
- **Estrategia de priorización estricta:**
  1. 🌟 **Wishlist:** `/giveaways/search?type=wishlist`
  2. 📦 **DLCs:** `/giveaways/search?dlc=true`
  3. 👥 **Grupos (Group):** `/giveaways/search?type=group`
  4. 📋 **Múltiples copias:** `/giveaways/search?copy_min=2`
  5. 🆕 **Nuevos:** `/giveaways/search?type=new`
- **Gestión eficiente de puntos:** Invierte los puntos disponibles según el orden de prioridad y detecta si ya se ha participado previamente (`is-faded`).
- **Doble interfaz de uso:**
  - 🌐 **Panel Web (FastAPI + HTMX):** Monitoreo en tiempo real, estadísticas, historial, ejecuciones pasadas y botón de lanzamiento manual.
  - 💻 **Cliente CLI (`cli.py`):** Ejecución directa desde terminal, diagnósticos de cuenta, estadísticas resumidas y exportación a CSV.
- **Respeto a rate limits y comportamiento humano:** Jitter aleatorio configurable (3-8 segundos entre participaciones) y delays entre categorías.
- **Base de datos SQLite optimizada:** Modo WAL (*Write-Ahead Logging*) y timeouts de conexión para operaciones concurrentes seguras.
- **Contenerización lista para producción:** `Dockerfile` con usuario no-root (`appuser`), límites de memoria y healthchecks en `compose.yml`.

---

## 📋 Requisitos Previos

- Python 3.12+ (para ejecución local)
- Docker y Docker Compose (para despliegue en servidor / Raspberry Pi)
- Cuenta activa en SteamGifts con puntos acumulados

---

## 🔑 Obtención de la Cookie `PHPSESSID`

1. Abre [SteamGifts](https://www.steamgifts.com) en tu navegador e inicia sesión con Steam.
2. Pulsa <kbd>F12</kbd> (o clic derecho → *Inspeccionar*).
3. Ve a la pestaña **Application** (en Chrome/Edge) o **Storage/Almacenamiento** (en Firefox).
4. En el menú izquierdo, despliega **Cookies** → `https://www.steamgifts.com`.
5. Localiza la fila con el nombre **`PHPSESSID`** y copia su valor.
6. Pega este valor en tu archivo `.env`:
   ```env
   STEAMGIFTS_PHPSESSID=tu_cookie_aqui
   ```

> [!WARNING]
> Tu cookie `PHPSESSID` equivale a tu sesión activa en SteamGifts. **Nunca la compartas ni la subas a repositorios públicos.**

---

## 🛠️ Instalación y Configuración Local

1. Clona el repositorio o accede a su carpeta:
   ```bash
   cd steamgifts
   ```
2. Crea y activa un entorno virtual de Python:
   ```bash
   # En Windows
   python -m venv .venv
   .venv\Scripts\activate

   # En Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```
4. Configura el archivo de entorno `.env`:
   ```bash
   cp .env.example .env
   # Edita .env y añade tu STEAMGIFTS_PHPSESSID
   ```

---

## 💻 Uso por Línea de Comandos (CLI)

El proyecto incluye el script `cli.py` para operar directamente desde la consola:

### 1. Diagnóstico de sesión (sin participar en sorteos)
Comprueba si la cookie es válida y muestra el usuario, puntos y nivel de cuenta:
```bash
python cli.py --check
```

### 2. Ejecutar una ronda completa del bot
Procesa todas las categorías en su orden de prioridad por defecto (Wishlist → DLC → Group → Multiple Copies → New):
```bash
python cli.py
```

### 3. Ejecutar solo categorías específicas
```bash
# Ejemplo: solo Wishlist y DLCs
python cli.py --categories wishlist dlc

# Ejemplo: con límite de 10 entradas
python cli.py --categories wishlist --max-entries 10
```

### 4. Consultar estadísticas de la base de datos
```bash
python cli.py --stats
```

### 5. Exportar el historial a un archivo CSV
```bash
python cli.py --export-csv entradas_steamgifts.csv
```

---

## 🌐 Uso de la Aplicación Web (FastAPI)

Para iniciar el servidor web local con recarga automática:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8085 --reload
```

Accede desde tu navegador a:
- **Panel de Control:** `http://localhost:8085/dashboard`
- **Historial de Entradas:** `http://localhost:8085/entries`
- **Registro de Ejecuciones:** `http://localhost:8085/runs`
- **Configuración y Diagnóstico:** `http://localhost:8085/config`
- **Documentación Interactiva Swagger:** `http://localhost:8085/docs`
- **Endpoint de vitalidad:** `http://localhost:8085/health`
- **Endpoint de disponibilidad:** `http://localhost:8085/ready`

---

## 🏗️ Arquitectura del Proyecto

```text
steamgifts/
├── app/
│   ├── main.py                  # Instancia FastAPI, lifespan, middlewares y montaje estático
│   ├── api/
│   │   ├── health.py            # Endpoints /health y /ready
│   │   └── v1/
│   │       ├── bot.py           # Endpoints de control del bot y diagnóstico
│   │       └── entries.py       # Endpoints de consulta de historial y estadísticas
│   ├── core/
│   │   ├── config.py            # Configuración tipada con Pydantic Settings (.env)
│   │   └── database.py          # Conexión SQLite con modo WAL y SessionLocal
│   ├── models/
│   │   └── entry.py             # Modelos SQLAlchemy: Entry y RunLog
│   ├── schemas/
│   │   └── giveaway.py          # Modelos Pydantic para validación y DTOs
│   ├── services/
│   │   ├── steamgifts_client.py # Cliente HTTP con requests y BeautifulSoup
│   │   └── bot_engine.py        # Orquestador del bot, delays y lógica de prioridades
│   └── web/
│       ├── routes.py            # Enrutador SSR y parciales HTMX
│       ├── static/
│       │   ├── css/style.css    # Estilos inspirados en Steam / SteamGifts
│       │   └── js/app.js        # Módulo JavaScript para interactividad
│       └── templates/
│           ├── base.html        # Layout base con navbar y badges en tiempo real
│           ├── dashboard.html   # Panel de control principal
│           ├── entries.html     # Historial de entradas con filtros
│           ├── runs.html        # Historial de ejecuciones
│           ├── run_detail.html  # Detalle de una ejecución concreta
│           ├── config.html      # Pantalla de configuración y diagnóstico
│           └── components/      # Fragmentos parciales para HTMX
│               ├── bot_status.html
│               ├── entries_table.html
│               ├── run_summary.html
│               ├── runs_table.html
│               ├── session_status.html
│               └── stats_cards.html
├── cli.py                       # Script CLI para terminal
├── tests/
│   ├── conftest.py              # Fixtures pytest y BD en memoria con StaticPool
│   ├── test_health.py           # Pruebas de endpoints /health y /ready
│   ├── test_api.py              # Pruebas funcionales de la API
│   └── test_web.py              # Pruebas de vistas HTML y parciales HTMX
├── compose.yml                  # Configuración Docker Compose con límites y healthcheck
├── Dockerfile                   # Imagen ligera Python 3.12 con usuario no-root
├── requirements.txt             # Dependencias con versiones fijadas
├── .env.example                 # Plantilla de variables de entorno
└── README.md
```

---

## 🐳 Despliegue en Producción (Docker Compose)

### 1. Preparar directorios en el servidor (ej. Raspberry Pi)
```bash
sudo mkdir -p /opt/apps/steamgifts /mnt/dietpi_userdata/apps/steamgifts/data /mnt/dietpi_userdata/backups/steamgifts
sudo chown -R dev:dev /opt/apps/steamgifts /mnt/dietpi_userdata/apps/steamgifts /mnt/dietpi_userdata/backups/steamgifts
```

### 2. Configurar y arrancar
```bash
cd /opt/apps/steamgifts
cp .env.example .env
nano .env  # Configurar STEAMGIFTS_PHPSESSID

docker compose up -d --build
```

El servicio quedará disponible en el puerto `8085` del servidor.

---

## 💾 Copias de Seguridad (Backup Seguro SQLite)

Debido al modo **WAL (*Write-Ahead Logging*)**, nunca debe copiarse el fichero `.db` directamente con `cp` mientras el servicio esté en ejecución.

**Comando canónico de respaldo en caliente:**
```bash
sqlite3 /mnt/dietpi_userdata/apps/steamgifts/data/database.db ".backup '/mnt/dietpi_userdata/backups/steamgifts/db_$(date +%Y%m%d_%H%M%S).db'"
```

---

## 🧪 Pruebas Automatizadas

Para ejecutar la batería completa de tests unitarios y funcionales:
```bash
python -m pytest -v
```

---

## ⚠️ Aviso Legal y Buenas Prácticas

SteamGifts prohíbe en sus Términos de Servicio el uso de scripts no autorizados para automatizar participaciones masivas. Esta herramienta implementa mecanismos de seguridad activa:
- Retardos aleatorios configurables (*jitter* humano entre 3 y 8 segundos).
- Pausas entre categorías.
- Límite máximo de participaciones por ejecución.
- Respeta los bloqueos de Cloudflare.

**Utiliza esta herramienta de forma responsable y bajo tu propio criterio.**

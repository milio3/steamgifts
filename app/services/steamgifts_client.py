"""Cliente HTTP para interactuar con SteamGifts.com mediante scraping y AJAX."""

import logging
import re
from typing import List, Optional

try:
    from curl_cffi import requests as http_requests
    from curl_cffi.requests.exceptions import (
        ConnectionError as HttpConnectionError,
        HTTPError as HttpHTTPError,
        Timeout as HttpTimeout,
    )
    HAS_CURL_CFFI = True
except ImportError:
    import requests as http_requests
    from requests.exceptions import (
        ConnectionError as HttpConnectionError,
        HTTPError as HttpHTTPError,
        Timeout as HttpTimeout,
    )
    HAS_CURL_CFFI = False

from bs4 import BeautifulSoup

from app.schemas.giveaway import AccountInfo, EntryResult, GiveawayInfo

logger = logging.getLogger(__name__)


class SteamGiftsClient:
    """Cliente que gestiona la sesión y las peticiones a SteamGifts."""

    def __init__(self, phpsessid: str, base_url: str, user_agent: str, timeout: float):
        if HAS_CURL_CFFI:
            self.session = http_requests.Session(impersonate="chrome120")
            logger.debug("Usando curl_cffi (impersonate='chrome120') para evadir Cloudflare TLS fingerprinting.")
        else:
            self.session = http_requests.Session()
            logger.debug("curl_cffi no disponible, usando requests estándar.")
        cookie_limpia = str(phpsessid).strip().strip('"').strip("'")
        self.phpsessid = cookie_limpia
        self.session.cookies.set("PHPSESSID", cookie_limpia, domain="www.steamgifts.com")
        self.session.cookies.set("PHPSESSID", cookie_limpia, domain=".steamgifts.com")
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Cookie": f"PHPSESSID={cookie_limpia}",
            "Connection": "keep-alive",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        })
        self.base_url = base_url
        self.timeout = timeout
        self._xsrf_token: Optional[str] = None

    def check_session(self) -> tuple[bool, str]:
        """Comprueba el estado de la sesión y retorna si es válida junto con el motivo detallado."""
        try:
            response = self.session.get(self.base_url, timeout=self.timeout)
            if response.status_code == 403:
                return (
                    False,
                    "Cloudflare ha bloqueado la petición (HTTP 403 Forbidden). La IP o las cabeceras han sido bloqueadas por Cloudflare.",
                )
            if response.status_code != 200:
                return (
                    False,
                    f"Respuesta HTTP inesperada de SteamGifts (Código {response.status_code}).",
                )

            # Si aparecen los puntos de navegación, el usuario está correctamente autenticado
            if "nav__points" in response.text:
                return True, "Sesión válida"

            # Si no hay puntos, verificar si Cloudflare interceptó con una pantalla de comprobación
            texto_lower = response.text.lower()
            if "<title>just a moment...</title>" in texto_lower or "cf-browser-verification" in texto_lower:
                return (
                    False,
                    "Cloudflare ha interceptado la conexión con una pantalla de comprobación de navegador ('Just a moment...').",
                )

            soup_title = re.search(r'<title>(.*?)</title>', response.text, re.IGNORECASE)
            titulo = soup_title.group(1).strip() if soup_title else "Sin título"
            logger.warning(f"Respuesta sin indicador de puntos. Título de página: '{titulo}', longitud HTML: {len(response.text)}")
            return (
                False,
                f"La cookie PHPSESSID ({self.phpsessid[:6]}...) no tiene sesión activa (Página devuelta: '{titulo}'). Verifica que la cookie sea la de tu sesión actual.",
            )
        except HttpConnectionError as e:
            return (
                False,
                f"Error de red o resolución DNS: No se pudo conectar a {self.base_url}. Verifica que el contenedor tenga acceso a Internet.",
            )
        except HttpTimeout:
            return (
                False,
                f"Tiempo de espera agotado al conectar a {self.base_url} (tras {self.timeout} segundos).",
            )
        except Exception as e:
            return False, f"Error inesperado al comprobar sesión: {e}"

    def is_session_valid(self) -> bool:
        """Verifica si la cookie PHPSESSID es válida comprobando elementos de usuario logueado."""
        valida, motivo = self.check_session()
        if not valida:
            logger.warning(f"Sesión no válida: {motivo}")
        return valida

    def get_account_info(self) -> AccountInfo:
        """Obtiene puntos, nivel, nombre de usuario y token XSRF de la cuenta."""
        try:
            response = self.session.get(self.base_url, timeout=self.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # Puntos disponibles
            puntos_elem = soup.select_one(".nav__points")
            puntos = int(puntos_elem.text.strip()) if puntos_elem else 0

            # Token XSRF (necesario para todas las acciones POST)
            token_elem = soup.select_one('input[name="xsrf_token"]')
            xsrf_token = token_elem["value"] if token_elem else None
            self._xsrf_token = xsrf_token

            # Nivel del usuario
            nivel_elem = soup.select_one("span[title]")
            nivel = 0
            if nivel_elem and nivel_elem.get("title"):
                try:
                    nivel = int(float(nivel_elem["title"]))
                except (ValueError, TypeError):
                    pass

            # Nombre de usuario
            avatar_elem = soup.select_one(".nav__avatar-outer-wrap")
            username = "Desconocido"
            if avatar_elem and avatar_elem.get("href"):
                partes = avatar_elem["href"].strip("/").split("/")
                if len(partes) >= 2:
                    username = partes[-1]

            logger.info(f"Cuenta: {username} | Puntos: {puntos} | Nivel: {nivel}")
            return AccountInfo(
                points=puntos, level=nivel, username=username, xsrf_token=xsrf_token
            )
        except Exception as e:
            logger.error(f"Error obteniendo información de la cuenta: {e}")
            raise

    def get_giveaways(
        self, category_url: str, category_name: str, page: int = 1
    ) -> List[GiveawayInfo]:
        """Obtiene la lista de giveaways de una categoría y página específica."""
        try:
            separador = "&" if "?" in category_url else "?"
            url = f"{self.base_url}{category_url}{separador}page={page}"

            logger.info(f"Escaneando {category_name} (pág. {page})")
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            # Comprobar si Cloudflare ha bloqueado la petición
            if "cf-browser-verification" in response.text or "just a moment" in response.text.lower():
                logger.error("Cloudflare ha bloqueado la petición. Usa una IP residencial.")
                return []

            soup = BeautifulSoup(response.text, "html.parser")

            # Actualizar token XSRF si lo encontramos
            token_elem = soup.select_one('input[name="xsrf_token"]')
            if token_elem:
                self._xsrf_token = token_elem["value"]

            giveaways = []
            filas = soup.select(".giveaway__row-inner-wrap")
            for fila in filas:
                gw = self._parse_giveaway_row(fila, category_name)
                if gw:
                    giveaways.append(gw)

            logger.info(
                f"  → {len(giveaways)} giveaways encontrados en {category_name} (pág. {page})"
            )
            return giveaways

        except HttpHTTPError as e:
            if e.response and e.response.status_code == 429:
                logger.warning(f"Rate limit alcanzado (429) en {category_name}")
            else:
                logger.error(f"Error HTTP obteniendo giveaways de {category_name}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error obteniendo giveaways de {category_name}: {e}")
            return []

    def enter_giveaway(self, code: str, game_name: str, xsrf_token: Optional[str] = None) -> EntryResult:
        """Envía la petición AJAX para entrar en un giveaway."""
        token = xsrf_token or self._xsrf_token
        if not token:
            return EntryResult(
                giveaway_code=code,
                game_name=game_name,
                result="error",
                error_message="No hay token XSRF disponible",
            )

        try:
            url = f"{self.base_url}/ajax.php"
            data = {
                "xsrf_token": token,
                "do": "entry_insert",
                "code": code,
            }
            headers = {
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": f"{self.base_url}/giveaway/{code}/",
            }

            response = self.session.post(
                url, data=data, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()
            json_resp = response.json()

            if json_resp.get("type") == "success":
                puntos = json_resp.get("points")
                logger.info(f"✅ Entrada exitosa: {game_name} │ Puntos restantes: {puntos}")
                return EntryResult(
                    giveaway_code=code,
                    game_name=game_name,
                    result="success",
                    points_remaining=int(puntos) if puntos is not None else None,
                )
            else:
                msg_error = json_resp.get("msg", "Error desconocido")
                logger.warning(f"[ERROR] Error al entrar en {game_name}: {msg_error}")
                return EntryResult(
                    giveaway_code=code,
                    game_name=game_name,
                    result="error",
                    error_message=msg_error,
                )

        except HttpHTTPError as e:
            if e.response and e.response.status_code == 429:
                logger.warning(f"Rate limit (429) al entrar en {game_name}")
                return EntryResult(
                    giveaway_code=code,
                    game_name=game_name,
                    result="error",
                    error_message="Rate limit alcanzado (429). Espera unos minutos.",
                )
            logger.error(f"Error HTTP al entrar en {game_name}: {e}")
            return EntryResult(
                giveaway_code=code,
                game_name=game_name,
                result="error",
                error_message=str(e),
            )
        except Exception as e:
            logger.error(f"Error inesperado al entrar en {game_name}: {e}")
            return EntryResult(
                giveaway_code=code,
                game_name=game_name,
                result="error",
                error_message=str(e),
            )

    def _parse_giveaway_row(
        self, row_element, category_name: str
    ) -> Optional[GiveawayInfo]:
        """Parsea una fila HTML de giveaway y extrae toda la información."""
        try:
            # Nombre y enlace del juego
            enlace = row_element.select_one("a.giveaway__heading__name")
            if not enlace:
                return None

            nombre = enlace.text.strip()
            url_juego = enlace.get("href", "")

            # Código del giveaway desde la URL
            codigo_match = re.search(r"/giveaway/([A-Za-z0-9]+)/", url_juego)
            if not codigo_match:
                return None
            codigo = codigo_match.group(1)

            # Coste en puntos y número de copias
            thin_elems = row_element.select(".giveaway__heading__thin")
            coste = 0
            copias = 1
            for elem in thin_elems:
                texto = elem.text.strip()
                # Buscar coste: (40P)
                coste_match = re.search(r"\((\d+)P\)", texto)
                if coste_match:
                    coste = int(coste_match.group(1))
                # Buscar copias: (50 Copies)
                copias_match = re.search(r"\((\d+)\s+Cop", texto)
                if copias_match:
                    copias = int(copias_match.group(1))

            # Número de participantes
            entradas = 0
            enlaces_info = row_element.select(".giveaway__links a")
            for a in enlaces_info:
                entradas_match = re.search(r"([\d,]+)\s+entr", a.text)
                if entradas_match:
                    entradas = int(entradas_match.group(1).replace(",", ""))
                    break

            # Tiempo restante
            tiempo_elem = row_element.select_one("span[data-timestamp]")
            tiempo_restante = "Desconocido"
            if tiempo_elem:
                tiempo_restante = tiempo_elem.text.strip()

            # Nivel requerido
            nivel_requerido = 0
            nivel_elem = row_element.select_one(
                "[class*='giveaway__column--contributor-level']"
            )
            if nivel_elem:
                nivel_match = re.search(r"Level\s+(\d+)", nivel_elem.text)
                if nivel_match:
                    nivel_requerido = int(nivel_match.group(1))
                # Si tiene clase --negative, el usuario no cumple el requisito
                if "negative" in " ".join(nivel_elem.get("class", [])):
                    return None  # Saltar giveaways que no podemos entrar

            # Comprobar si ya hemos entrado (clase is-faded en el padre)
            padre = row_element.parent
            clases_padre = " ".join(padre.get("class", [])) if padre else ""
            ya_entrado = "is-faded" in clases_padre

            return GiveawayInfo(
                game_name=nombre,
                giveaway_code=codigo,
                giveaway_url=f"{self.base_url}{url_juego}",
                points_cost=coste,
                entries_count=entradas,
                copies=copias,
                time_remaining=tiempo_restante,
                category=category_name,
                level_required=nivel_requerido,
                is_entered=ya_entrado,
            )

        except Exception as e:
            logger.error(f"Error parseando fila de giveaway: {e}")
            return None

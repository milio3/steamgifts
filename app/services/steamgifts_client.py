"""Cliente HTTP para interactuar con SteamGifts.com mediante scraping y AJAX."""

import logging
import re
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from app.schemas.giveaway import AccountInfo, EntryResult, GiveawayInfo

logger = logging.getLogger(__name__)


class SteamGiftsClient:
    """Cliente que gestiona la sesión y las peticiones a SteamGifts."""

    def __init__(self, phpsessid: str, base_url: str, user_agent: str, timeout: float):
        self.session = requests.Session()
        self.session.cookies.set("PHPSESSID", phpsessid, domain="www.steamgifts.com")
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })
        self.base_url = base_url
        self.timeout = timeout
        self._xsrf_token: Optional[str] = None

    def is_session_valid(self) -> bool:
        """Verifica si la cookie PHPSESSID es válida comprobando elementos de usuario logueado."""
        try:
            response = self.session.get(self.base_url, timeout=self.timeout)
            if response.status_code != 200:
                logger.warning(f"Respuesta HTTP {response.status_code} al verificar sesión")
                return False
            # Si hay nav__points, el usuario está logueado
            valida = "nav__points" in response.text
            if not valida:
                logger.warning("Sesión inválida: no se encontró el indicador de puntos")
            return valida
        except Exception as e:
            logger.error(f"Error comprobando sesión: {e}")
            return False

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

        except requests.exceptions.HTTPError as e:
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

        except requests.exceptions.HTTPError as e:
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

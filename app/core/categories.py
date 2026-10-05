"""Gestión centralizada de categorías, prioridades y persistencia del orden."""

import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)

# Definición de las 7 categorías soportadas con sus metadatos e iconos SVG de Tailwind (Heroicons)
AVAILABLE_CATEGORIES: Dict[str, dict] = {
    "wishlist": {
        "name": "Wishlist",
        "label": "Wishlist",
        "url": "/giveaways/search?type=wishlist",
        "badge_class": "badge-wishlist",
        "icon": "bi-star-fill",
        "svg_icon": '<svg class="tailwind-svg-icon" xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 24 24"><path d="M11.48 3.499a.562.562 0 0 1 1.04 0l2.125 5.111a.563.563 0 0 0 .475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 0 0-.182.557l1.285 5.385a.562.562 0 0 1-.84.61l-4.725-2.885a.562.562 0 0 0-.586 0L6.982 20.54a.562.562 0 0 1-.84-.61l1.285-5.386a.562.562 0 0 0-.182-.557l-4.204-3.602a.562.562 0 0 1 .321-.988l5.518-.442a.563.563 0 0 0 .475-.345L11.48 3.5Z" /></svg>',
    },
    "dlc": {
        "name": "DLC",
        "label": "DLC",
        "url": "/giveaways/search?dlc=true",
        "badge_class": "badge-dlc",
        "icon": "bi-box-seam",
        "svg_icon": '<svg class="tailwind-svg-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.75" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="m21 7.5-9-5.25L3 7.5m18 0-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" /></svg>',
    },
    "group": {
        "name": "Group",
        "label": "Group",
        "url": "/giveaways/search?type=group",
        "badge_class": "badge-group",
        "icon": "bi-people-fill",
        "svg_icon": '<svg class="tailwind-svg-icon" xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 24 24"><path d="M4.5 6.375a4.125 4.125 0 1 1 8.25 0 4.125 4.125 0 0 1-8.25 0ZM14.25 8.625a3.375 3.375 0 1 1 6.75 0 3.375 3.375 0 0 1-6.75 0ZM1.5 19.125a7.125 7.125 0 0 1 14.25 0v.003l-.001.119a.75.75 0 0 1-.363.633 13.067 13.067 0 0 1-6.761 1.87 13.067 13.067 0 0 1-6.76-1.87.75.75 0 0 1-.364-.633l-.001-.122ZM17.25 19.128l-.001.144a2.25 2.25 0 0 1-.233.96 10.088 10.088 0 0 0 5.06-1.604.75.75 0 0 0 .424-.658v-.108a5.625 5.625 0 0 0-5.25-5.612v6.878Z" /></svg>',
    },
    "multiple_copies": {
        "name": "Multiple Copies",
        "label": "Multiple Copies",
        "url": "/giveaways/search?copy_min=2",
        "badge_class": "badge-multiple",
        "icon": "bi-files",
        "svg_icon": '<svg class="tailwind-svg-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.75" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 0 1-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 0 1 1.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 0 0-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 0 1-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 0 0-3.375-3.375h-1.5a1.125 1.125 0 0 1-1.125-1.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H9.75" /></svg>',
    },
    "recommended": {
        "name": "Recommended",
        "label": "Recommended",
        "url": "/giveaways/search?type=recommended",
        "badge_class": "badge-recommended",
        "icon": "bi-hand-thumbs-up-fill",
        "svg_icon": '<svg class="tailwind-svg-icon" xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 24 24"><path d="M7.493 18.5c-.425 0-.82-.236-.975-.632A7.48 7.48 0 0 1 6 15.125c0-1.757.599-3.376 1.606-4.664.19-.243.203-.578.034-.834l-.454-.68c-.287-.43-.198-1.01.21-1.328a6.002 6.002 0 0 1 5.394-1.116c.394.095.795-.098.966-.466l.72-1.545A2.25 2.25 0 0 1 16.51 3c1.077 0 1.99.764 2.186 1.825l.487 2.63c.068.368.375.645.748.645h1.319c1.242 0 2.25 1.008 2.25 2.25 0 .285-.053.558-.15.809l-1.91 4.965A3.75 3.75 0 0 1 17.94 18.5H7.493ZM2.25 7.5a1.5 1.5 0 0 1 1.5-1.5h.75a1.5 1.5 0 0 1 1.5 1.5v10.5a1.5 1.5 0 0 1-1.5 1.5h-.75a1.5 1.5 0 0 1-1.5-1.5V7.5Z" /></svg>',
    },
    "new": {
        "name": "New",
        "label": "New",
        "url": "/giveaways/search?type=new",
        "badge_class": "badge-new",
        "icon": "bi-lightning-fill",
        "svg_icon": '<svg class="tailwind-svg-icon" xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M14.615 1.595a.75.75 0 0 1 .359.852L12.982 9.75h7.268a.75.75 0 0 1 .548 1.262l-10.5 11.25a.75.75 0 0 1-1.272-.71l1.992-7.302H3.75a.75.75 0 0 1-.548-1.262l10.5-11.25a.75.75 0 0 1 .913-.143Z" clip-rule="evenodd" /></svg>',
    },
    "all": {
        "name": "All",
        "label": "All",
        "url": "/giveaways/search",
        "badge_class": "badge-all",
        "icon": "bi-globe",
        "svg_icon": '<svg class="tailwind-svg-icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.75" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0 1 12 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 0 1 3 12c0-1.605.42-3.113 1.157-4.418" /></svg>',
    },
}

# Alias para compatibilidad con llamadas que usen la variante con mayúsculas y espacios
AVAILABLE_CATEGORIES["Multiple Copies"] = AVAILABLE_CATEGORIES["multiple_copies"]

# Orden inicial por defecto especificado por el usuario (1 a 7)
DEFAULT_CATEGORY_ORDER: List[str] = [
    "wishlist",
    "dlc",
    "group",
    "multiple_copies",
    "recommended",
    "new",
    "all",
]


def load_categories_config() -> Tuple[List[str], Set[str]]:
    """Carga el orden y las categorías habilitadas exclusivamente desde settings (.env)."""
    from app.core.config import settings

    raw_order = None
    if getattr(settings, "CATEGORIES_ORDER", None):
        raw_order = [c.strip() for c in settings.CATEGORIES_ORDER.split(",") if c.strip()]

    if raw_order:
        # Normalizar si viniese 'Multiple Copies' con mayúsculas/espacios
        order = ["multiple_copies" if c in ("Multiple Copies", "multiple copies") else c for c in raw_order]
        # Filtrar categorías válidas eliminando duplicados preservando orden
        valid_order = []
        for c in order:
            if c in AVAILABLE_CATEGORIES and c not in valid_order:
                valid_order.append(c)
        for c in DEFAULT_CATEGORY_ORDER:
            if c not in valid_order:
                valid_order.append(c)
        enabled = set(valid_order)
        return valid_order, enabled

    return list(DEFAULT_CATEGORY_ORDER), set(DEFAULT_CATEGORY_ORDER)


def save_categories_config(order: List[str], enabled: List[str]) -> bool:
    """Guarda el orden y categorías habilitadas exclusivamente en .env."""
    norm_order = ["multiple_copies" if c in ("Multiple Copies", "multiple copies") else c for c in order]
    valid_order = []
    for c in norm_order:
        if c in AVAILABLE_CATEGORIES and c not in valid_order:
            valid_order.append(c)

    for c in DEFAULT_CATEGORY_ORDER:
        if c not in valid_order:
            valid_order.append(c)

    # Persistir exclusivamente en .env
    try:
        from app.core.config import update_settings_and_env
        update_settings_and_env({"CATEGORIES_ORDER": ",".join(valid_order)})
        return True
    except Exception as e:
        logger.error(f"Error guardando orden de categorías en .env: {e}")
        return False

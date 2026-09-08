"""Helpers y mapeos para zonas de inyección (code_conventions.md §4.2).

Las etiquetas e imágenes no entran en domain/constants.py (§4.2):
son artefactos de presentación, no conceptos de dominio.
"""

from pathlib import Path
from DayBetes_food.domain.constants import InjectionZone

BASE_INJECTION_ZONE_IMAGE = "/images/content/injection_zones/injection_zones.svg"

# Mapeos enum → presentación (diccionarios tipados, code_conventions.md §3.2)
INJECTION_ZONE_IMAGE_BY_ZONE: dict[InjectionZone, str] = {
    InjectionZone.RIGHT_ARM: "/images/content/injection_zones/injection_zones_right_arm.svg",
    InjectionZone.LEFT_ARM: "/images/content/injection_zones/injection_zones_left_arm.svg",
    InjectionZone.RIGHT_THIGH: "/images/content/injection_zones/injection_zones_right_thigh.svg",
    InjectionZone.LEFT_THIGH: "/images/content/injection_zones/injection_zones_left_thigh.svg",
    InjectionZone.ABDOMEN: "/images/content/injection_zones/injection_zones_abdomen.svg",
    InjectionZone.RIGHT_GLUTEUS: "/images/content/injection_zones/injection_zones_right_gluteus.svg",
    InjectionZone.LEFT_GLUTEUS: "/images/content/injection_zones/injection_zones_left_gluteus.svg",
}

INJECTION_ZONE_LABEL_BY_ZONE: dict[InjectionZone, str] = {
    InjectionZone.RIGHT_ARM: "Right arm",
    InjectionZone.LEFT_ARM: "Left arm",
    InjectionZone.RIGHT_THIGH: "Right thigh",
    InjectionZone.LEFT_THIGH: "Left thigh",
    InjectionZone.ABDOMEN: "Abdomen",
    InjectionZone.RIGHT_GLUTEUS: "Right gluteus",
    InjectionZone.LEFT_GLUTEUS: "Left gluteus",
}


def asset_busted(path: str) -> str:
    """Añade cache busting (timestamp) a rutas de assets estáticos."""
    static_root = Path(__file__).resolve().parents[1] / "static"
    rel = path[1:] if path.startswith("/") else path
    full = static_root / rel
    if not full.exists():
        return path
    return f"{path}?v={int(full.stat().st_mtime)}"


def injection_zone_label(zone: InjectionZone | None) -> str:
    """Etiqueta legible para una zona de inyección.

    Si zone es None (no registrada), devuelve "Zone not recorded".
    """
    return INJECTION_ZONE_LABEL_BY_ZONE[zone] if zone else "Zone not recorded"


def injection_zone_image(zone: InjectionZone | None) -> str:
    """Imagen/ícono para una zona de inyección.

    Si zone es None (no registrada), devuelve BASE_INJECTION_ZONE_IMAGE.
    """
    return INJECTION_ZONE_IMAGE_BY_ZONE[zone] if zone else BASE_INJECTION_ZONE_IMAGE


def parse_injection_zone(value) -> InjectionZone | None:
    """Convierte a InjectionZone un valor de presentación (cadena de BD o enum).

    Tolerante por diseño: es capa de presentación. Un valor no reconocido se pinta
    como "zona no registrada", no revienta la página. La validación dura vive en el
    CHECK de base de datos y en database/mappers.py (§4.3).
    """
    if isinstance(value, InjectionZone):
        return value
    raw = (value or "").strip().lower()
    if not raw:
        return None
    try:
        return InjectionZone(raw)
    except ValueError:
        return None

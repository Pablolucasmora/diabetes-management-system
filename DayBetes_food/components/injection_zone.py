"""Helpers and mappings for injection zones (code_conventions.md §4.2).

The labels and images do not go into domain/constants.py (§4.2): they are
presentation artifacts, not domain concepts.
"""

from pathlib import Path
from DayBetes_food.domain.constants import InjectionZone

BASE_INJECTION_ZONE_IMAGE = "/images/content/injection_zones/injection_zones.svg"

# Enum → presentation mappings (typed dictionaries, code_conventions.md §3.2)
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
    """Add cache busting (timestamp) to static asset paths."""
    static_root = Path(__file__).resolve().parents[1] / "static"
    rel = path[1:] if path.startswith("/") else path
    full = static_root / rel
    if not full.exists():
        return path
    return f"{path}?v={int(full.stat().st_mtime)}"


def injection_zone_label(zone: InjectionZone | None) -> str:
    """Readable label for an injection zone.

    If zone is None (not recorded), it returns "Zone not recorded".
    """
    return INJECTION_ZONE_LABEL_BY_ZONE[zone] if zone else "Zone not recorded"


def injection_zone_image(zone: InjectionZone | None) -> str:
    """Image/icon for an injection zone.

    If zone is None (not recorded), it returns BASE_INJECTION_ZONE_IMAGE.
    """
    return INJECTION_ZONE_IMAGE_BY_ZONE[zone] if zone else BASE_INJECTION_ZONE_IMAGE


def parse_injection_zone(value) -> InjectionZone | None:
    """Convert a presentation value (DB string or enum) to InjectionZone.

    Lenient by design: it is the presentation layer. An unrecognized value is
    drawn as "zone not recorded" and does not break the page. Strict
    validation lives in the database CHECK and in database/mappers.py (§4.3).
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

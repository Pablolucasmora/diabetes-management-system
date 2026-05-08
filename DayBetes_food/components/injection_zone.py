from pathlib import Path

INJECTION_ZONE_IMAGE_BY_KEY = {
    "right_arm": "/images/content/injection_zones/injection_zones_right_arm.svg",
    "left_arm": "/images/content/injection_zones/injection_zones_left_arm.svg",
    "right_thigh": "/images/content/injection_zones/injection_zones_right_thigh.svg",
    "left_thigh": "/images/content/injection_zones/injection_zones_left_thigh.svg",
    "abdomen": "/images/content/injection_zones/injection_zones_abdomen.svg",
    "right_gluteus": "/images/content/injection_zones/injection_zones_right_gluteus.svg",
    "left_gluteus": "/images/content/injection_zones/injection_zones_left_gluteus.svg",
}

INJECTION_ZONE_LABEL_BY_KEY = {
    "right_arm": "Right arm",
    "left_arm": "Left arm",
    "right_thigh": "Right thigh",
    "left_thigh": "Left thigh",
    "abdomen": "Abdomen",
    "right_gluteus": "Right gluteus",
    "left_gluteus": "Left gluteus",
}

BASE_INJECTION_ZONE_IMAGE = "/images/content/injection_zones/injection_zones.svg"


def asset_busted(path: str) -> str:
    static_root = Path(__file__).resolve().parents[1] / "static"
    rel = path[1:] if path.startswith("/") else path
    full = static_root / rel
    if not full.exists():
        return path
    return f"{path}?v={int(full.stat().st_mtime)}"

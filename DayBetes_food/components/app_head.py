"""What makes the page installable as an app (frontend_conventions.md §11): the
manifest, its icons and the tags of the page's head, shared by every page."""

APP_NAME = "DayBetes"
# The `page` colour of static/css/input.css: a manifest and a meta tag cannot read it.
APP_THEME_COLOR = "#fbf8f3"
MANIFEST_PATH = "/manifest.webmanifest"
_ICON_PATH = "/images/ui/app_icon_{size}.png"

APP_HEAD_HTML = f"""<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta name="theme-color" content="{APP_THEME_COLOR}">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-title" content="{APP_NAME}">
    <link rel="manifest" href="{MANIFEST_PATH}">
    <link rel="apple-touch-icon" href="{_ICON_PATH.format(size=180)}">"""


def app_manifest() -> dict:
    """The manifest of the installed app. The icon's drawing is inside the safe
    zone, so the large one is also the maskable one."""
    return {
        "id": "/",
        "name": APP_NAME,
        "short_name": APP_NAME,
        "start_url": "/menu",
        "scope": "/",
        "display": "standalone",
        "lang": "en",
        "background_color": APP_THEME_COLOR,
        "theme_color": APP_THEME_COLOR,
        "icons": [
            {"src": _ICON_PATH.format(size=192), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": _ICON_PATH.format(size=512), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": _ICON_PATH.format(size=512), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }

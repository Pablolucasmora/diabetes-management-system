"""Navigation at the end of an htmx request (code_conventions.md §9.4).

`HX-Location` changes the page like any other link of the web: the new page
goes into `#main_content` and into the history, without reloading, so Back
still works (frontend_conventions.md §5). `HX-Redirect`, a full reload, is
only for starting over: logging in, out or a session that changes.
"""

import json


def hx_location(path: str) -> dict[str, str]:
    """Headers that take the browser to `path` as a page of the web."""
    location = {"path": path, "target": "#main_content", "swap": "innerHTML", "push": True}
    return {"HX-Location": json.dumps(location)}

def back_js(fallback_url: str) -> str:
    """Click handler of every "Back" button (static/js/navigation.js).

    It goes back in the history; `fallback_url` is the page's parent, opened
    only when there is no page of the web behind (frontend_conventions.md §5).
    """
    return f"dbBack('{fallback_url}');"

"""Routes accept only the HTTP method they declare (code_conventions.md §9.2).

FastHTML takes the method from the function's name, but only for top-level functions:
a `def post` nested in `setup_*_routes` is registered with GET and POST, so a request
could write through a method the CSRF check does not cover. Every route goes through
`single_method_rt`, and `check_single_method_routes` stops the startup if one avoids it.
"""

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
# Starlette adds HEAD to every GET route: it runs the same read.
_IMPLICIT_METHODS = frozenset({"HEAD"})


def single_method_rt(rt):
    """Wrap FastHTML's `rt` so a route's method is the name of its function."""

    def route(path: str, **options):
        def register(function):
            method = function.__name__
            if method not in _HTTP_METHODS:
                raise ValueError(f"Route {path}: the function must be named after its HTTP method, not {method!r}")
            return rt(path, methods=[method], **options)(function)

        return register

    return route


def check_single_method_routes(routes) -> None:
    """Fail at startup if any route accepts more than one method."""
    for route in routes:
        methods = set(getattr(route, "methods", None) or ()) - _IMPLICIT_METHODS
        if len(methods) > 1:
            raise RuntimeError(f"Route {route.path} accepts several HTTP methods: {sorted(methods)}")

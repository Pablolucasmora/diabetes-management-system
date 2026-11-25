"""Security headers of every response (code_conventions.md §5.5)."""

# Second barrier against injected markup. Scripts still allow inline code and
# eval: the pages use inline handlers and hx-on, which a nonce-based policy
# would block. The hosts are the CDNs the pages load from (components/ui.py,
# tags_settings.py, static/js/scanner.js).
_SCRIPT_HOSTS = "https://cdn.jsdelivr.net https://fastly.jsdelivr.net https://unpkg.com https://esm.sh"
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        f"script-src 'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' {_SCRIPT_HOSTS}",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        f"connect-src 'self' {_SCRIPT_HOSTS}",
        "worker-src 'self' blob:",
        "media-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
}


def add_security_headers(response):
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response

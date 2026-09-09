from backend import main as backend_main

app = backend_main.app

# Production Vercel entrypoint: the workspace is intentionally open-access.
# Remove the legacy private sign-in middleware and routes while preserving
# the app's response security headers and all Google OAuth/integration routes.
_AUTH_PATHS = {"/api/auth/login", "/api/auth/logout", "/api/auth/session"}

app.user_middleware = [
    middleware
    for middleware in app.user_middleware
    if middleware.kwargs.get("dispatch") is not backend_main.security
]
app.router.routes = [
    route for route in app.router.routes if getattr(route, "path", None) not in _AUTH_PATHS
]
app.middleware_stack = None


@app.middleware("http")
async def public_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.update({
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self' 'unsafe-inline'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        ),
    })
    return response

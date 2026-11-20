import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or not request.url.path.startswith("/api"):
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        sensitive = request.url.path in {"/api/auth/login", "/api/auth/register", "/api/auth/forgot-password", "/api/auth/reset-password"}
        limit = settings.auth_rate_limit_per_minute if sensitive else settings.rate_limit_per_minute
        key = f"{ip}:{'auth' if sensitive else 'api'}"
        now = time.monotonic()
        window = self.hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= limit:
            return JSONResponse({"detail": "Too many requests. Please slow down and try again shortly."}, status_code=429, headers={"Retry-After": "60"})
        window.append(now)
        return await call_next(request)

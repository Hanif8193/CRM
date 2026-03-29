"""
Sliding-Window Rate Limiter Middleware — فی IP درخواستوں کی حد

ہر IP سے max_requests درخواستیں window_seconds میں قبول کرتا ہے۔
حد پار ہونے پر HTTP 429 واپس کرتا ہے اور Retry-After ہیڈر شامل کرتا ہے۔

نوٹ: یہ in-memory store ایک process کے لیے ہے۔
Multi-process یا multi-server setup کے لیے Redis استعمال کریں۔
"""

import logging
import time
from collections import defaultdict, deque  # sliding window کے لیے

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger(__name__)

# یہ paths کبھی rate limit نہیں ہوتے (health checks، docs، admin، وغیرہ)
_EXEMPT_EXACT = frozenset({
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/health",
    "/api/metrics",
})

# یہ prefixes بھی exempt ہیں (سب paths جو ان سے شروع ہوں)
_EXEMPT_PREFIXES = (
    "/api/admin/",
    "/api/memory/",
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter۔

    Args:
        max_requests:   ونڈو میں زیادہ سے زیادہ درخواستیں (default: 5)
        window_seconds: ونڈو کا سائز سیکنڈوں میں (default: 60)

    مثال: max_requests=5, window_seconds=60 → 60 سیکنڈ میں 5 درخواستیں
    """

    def __init__(self, app, max_requests: int = 5, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests   = max_requests
        self.window_seconds = window_seconds
        # ہر IP کے لیے timestamp کی queue (monotonic time)
        # {ip: deque([t1, t2, t3, ...])}
        self._windows: dict[str, deque] = defaultdict(deque)

    # ──────────────────────────────────────────────────────────────────────────
    # Helper — client IP نکالنا
    # ──────────────────────────────────────────────────────────────────────────

    def _client_ip(self, request: Request) -> str:
        """
        Client کا IP address نکالیں۔

        اگر X-Forwarded-For ہیڈر ہے (nginx/reverse proxy) تو اسے ترجیح دیں۔
        ورنہ براہ راست request.client.host استعمال کریں۔
        """
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # پہلا IP لیں (کئی proxies کی صورت میں comma separated ہوتا ہے)
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    # ──────────────────────────────────────────────────────────────────────────
    # dispatch — ہر درخواست یہاں سے گزرتی ہے
    # ──────────────────────────────────────────────────────────────────────────

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Middleware کا مرکزی فنکشن۔

        Sliding window الگورتھم:
        1. پرانے timestamps ہٹائیں (window سے باہر)
        2. موجودہ window کی گنتی چیک کریں
        3. حد پار ہو → 429 واپس کریں
        4. حد کے اندر → timestamp شامل کریں اور آگے بھیجیں
        """
        # exempt paths بغیر check کے آگے بھیجیں
        path = request.url.path
        if path in _EXEMPT_EXACT or any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        ip  = self._client_ip(request)
        now = time.monotonic()  # monotonic clock — system time تبدیلی سے محفوظ
        window = self._windows[ip]

        # پرانے timestamps ہٹائیں (window سے باہر گر چکے ہیں)
        cutoff = now - self.window_seconds
        while window and window[0] <= cutoff:
            window.popleft()  # بائیں سے پرانے نکالیں

        # حد پار ہو گئی؟
        if len(window) >= self.max_requests:
            # کتنا وقت باقی ہے جب تک oldest timestamp expire نہ ہو
            retry_after = max(1, int(self.window_seconds - (now - window[0])) + 1)

            log.warning(
                "Rate limit پار ہو گئی ip=%s path=%s window_count=%d",
                ip,
                request.url.path,
                len(window),
            )

            # HTTP 429 — بہت زیادہ درخواستیں
            return Response(
                content='{"detail":"بہت زیادہ درخواستیں — تھوڑی دیر بعد دوبارہ کوشش کریں۔"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(retry_after)},  # کتنے سیکنڈ انتظار کریں
            )

        # حد کے اندر — موجودہ وقت شامل کریں اور آگے بھیجیں
        window.append(now)
        return await call_next(request)

"""
pytest configuration and shared fixtures.

Key design decisions:
  - DB and Kafka are fully mocked — no external services needed.
  - `client` is session-scoped (app created once = fast).
  - `reset_rate_limiter` is function-scoped autouse — clears the in-memory
    sliding window before every test so earlier tests don't consume quota
    for later ones (the rate limiter shares state across the session).
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure backend/ is on sys.path so absolute imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Mock DB ────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    """Mock database so tests never need a real PostgreSQL server."""
    monkeypatch.setattr("database.connection._pool", None)
    monkeypatch.setattr("database.connection.is_db_available", lambda: False)


# ── Mock Kafka ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_kafka(monkeypatch):
    """Prevent Kafka producer from connecting during tests."""
    monkeypatch.setattr("kafka.producer._producer", None)


# ── FastAPI test client (session-scoped = created once for all tests) ──────────

@pytest.fixture(scope="session")
def client():
    """
    Session-scoped TestClient.
    The app is built once and reused — much faster than per-test setup.
    """
    with (
        patch("database.connection.init_db"),
        patch("database.connection.close_db"),
        patch("kafka.producer.init_producer", new_callable=AsyncMock),
        patch("kafka.producer.close_producer", new_callable=AsyncMock),
    ):
        from main import app
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


# ── Rate limiter reset (function-scoped autouse) ───────────────────────────────

def _find_rate_limiter():
    """
    Traverse the built ASGI middleware stack and return the
    RateLimitMiddleware instance, or None if not found.

    The stack looks like:
        ServerErrorMiddleware
          → ExceptionMiddleware
            → CORSMiddleware
              → RateLimitMiddleware   ← we want this
                → Router
    """
    from middleware.rate_limit import RateLimitMiddleware
    try:
        from main import app
        node = app.middleware_stack
        while node is not None:
            if isinstance(node, RateLimitMiddleware):
                return node
            node = getattr(node, "app", None)
    except Exception:
        pass
    return None


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """
    Clear the rate limiter's sliding window before every test.

    WHY THIS IS NEEDED:
    The session-scoped TestClient reuses the same RateLimitMiddleware
    instance for the entire test run. The in-memory `_windows` dict
    accumulates request counts across tests. Without this reset, the
    5 validation tests that POST to /api/message fill up the default
    quota of 5, causing all later tests on that path to get HTTP 429.
    """
    limiter = _find_rate_limiter()
    if limiter is not None:
        limiter._windows.clear()
    yield
    # clean up after the test too (prevents bleed into next test)
    if limiter is not None:
        limiter._windows.clear()


# ── Agent mock helper ──────────────────────────────────────────────────────────

def make_agent_result(
    response: str = "Thank you for contacting us.",
    intent: str = "product",
    escalated: bool = False,
    source: str = "docs",
    priority: str = "low",
    escalation_reason: str = "",
) -> dict:
    """Return a minimal agent result dict matching simple_agent.run_agent output."""
    return {
        "response":          response,
        "intent":            intent,
        "escalated":         escalated,
        "source":            source,
        "priority":          priority,
        "escalation_reason": escalation_reason,
    }

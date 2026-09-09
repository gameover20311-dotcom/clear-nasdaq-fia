import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import fastapi
import httpx
import starlette
from fastapi.testclient import TestClient

from fia.oos_guard import durability_guard_status
from fia.provider_guard import guarded_get


class _Fake429Client:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None, headers=None):
        type(self).calls += 1
        req = httpx.Request("GET", url)
        response = httpx.Response(429, headers={"retry-after": "120"}, request=req)
        raise httpx.HTTPStatusError("rate limited", request=req, response=response)


class A2ZHardeningTests(unittest.TestCase):
    def test_patched_web_stack_is_loaded(self):
        self.assertGreaterEqual(tuple(map(int, fastapi.__version__.split(".")[:3])), (0, 141, 1))
        self.assertGreaterEqual(tuple(map(int, starlette.__version__.split(".")[:3])), (1, 3, 1))

    def test_provider_429_trips_host_cooldown(self):
        _Fake429Client.calls = 0
        hub = SimpleNamespace()
        with patch("fia.provider_guard.httpx.AsyncClient", _Fake429Client):
            first = asyncio.run(guarded_get(hub, "https://provider.example/v1/data", params={"token": "SECRET"}))
            second = asyncio.run(guarded_get(hub, "https://provider.example/v1/other", params={"token": "SECRET"}))
        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertEqual(_Fake429Client.calls, 1)

    def test_durability_failure_blocks_scientific_append(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://example.invalid/db",
            "FIA_FORWARD_OOS_DURABLE_REQUIRED": "1",
            "FIA_FORWARD_OOS_DURABLE_EXPIRES_AT": "2026-10-07T17:34:55.940151+00:00",
        }, clear=False), patch(
            "fia.forward_oos_durable.durability_status",
            return_value={"durable": False, "storage": "POSTGRES", "error": "UNAVAILABLE"},
        ):
            status = durability_guard_status(__import__("pathlib").Path("."))
        self.assertTrue(status["required_for_scientific_append"])
        self.assertFalse(status["append_allowed"])

    def test_run_once_is_not_anonymous(self):
        import main
        with patch("fia.forward_oos_api.run_once", new=AsyncMock(return_value={"ok": True})) as mocked:
            client = TestClient(main.app)
            response = client.post("/api/forward-oos/run-once")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json().get("detail"), "AUTH_REQUIRED")
        mocked.assert_not_awaited()

    def test_cors_rejects_untrusted_origin_and_accepts_production_frontend(self):
        import main
        client = TestClient(main.app)
        bad = client.options(
            "/api/health",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertNotEqual(bad.headers.get("access-control-allow-origin"), "https://evil.example")

        good = client.options(
            "/api/health",
            headers={
                "Origin": "https://clear-nasdaq-fia.vercel.app",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(
            good.headers.get("access-control-allow-origin"),
            "https://clear-nasdaq-fia.vercel.app",
        )

    def test_health_route_survives_hardening(self):
        import main
        response = TestClient(main.app).get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("ok"))


if __name__ == "__main__":
    unittest.main()

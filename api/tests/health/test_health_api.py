"""health 설계안 8절 (H1, H2)."""

import os
import unittest
from unittest import mock

from api.tests.support import client_for, make_app


class HealthApiTest(unittest.IsolatedAsyncioTestCase):
    async def test_h1_health_ok_without_api_key(self):
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with mock.patch.dict(os.environ, env, clear=True):
            async with client_for(make_app()) as c:
                r = await c.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"success": True, "data": {"status": "ok"}})

    async def test_h2_post_is_method_not_allowed(self):
        async with client_for(make_app()) as c:
            r = await c.post("/health")
        self.assertEqual(r.status_code, 405)
        body = r.json()
        self.assertEqual((body["success"], body["error_code"]), (False, "METHOD_NOT_ALLOWED"))
        self.assertEqual(set(body), {"success", "error_code", "message"})


if __name__ == "__main__":
    unittest.main()

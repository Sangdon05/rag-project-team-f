"""scripts/frontend/write_runtime_config.py: FRONTEND_API_BASE_URL → frontend/runtime-config.mjs."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("write_runtime_config", ROOT / "scripts/frontend/write_runtime_config.py")
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class RuntimeConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "runtime-config.mjs"

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_origin_without_trailing_slash(self):
        self.assertEqual(mod.write(" http://15.164.172.89/ ", self.out), "http://15.164.172.89")
        self.assertIn('export const API_BASE_URL = "http://15.164.172.89";', self.out.read_text(encoding="utf-8"))

    def test_keeps_port_and_https(self):
        self.assertEqual(mod.write("https://api.example.test:8443", self.out), "https://api.example.test:8443")

    def test_empty_value_removes_file(self):
        self.out.write_text("old", encoding="utf-8")
        self.assertIsNone(mod.write("", self.out))
        self.assertFalse(self.out.exists())
        self.assertIsNone(mod.write(None, self.out))

    def test_rejects_non_origin_values(self):
        for bad in ("ftp://host", "15.164.172.89", "http://host/api", "http://host?x=1",
                    "http://user:pw@host", "http://host:notaport", 'http://host";alert(1)//'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                mod.write(bad, self.out)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()

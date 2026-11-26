"""Check the Solar Compose init contract without Docker, DB or credentials."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INITDIR = "/docker-entrypoint-initdb.d"
SCHEMA_TARGET = "/docker-init-resources/solar_handoff.sql"


class SolarComposeInitTest(unittest.TestCase):
    def test_readonly_mounts_and_single_entrypoint_script(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        # Restrict inspection to the postgres volume block; no Compose interpolation.
        block = re.search(r"(?ms)^    volumes:\s*\n(.*?)(?=^    \w|^\w)", compose)
        self.assertIsNotNone(block)
        assert block is not None
        mounts = [m.strip().strip('"\'') for m in re.findall(
            r"^\s*-\s+([^\n#]+)", block.group(1), re.MULTILINE
        )]
        self.assertCountEqual(mounts, [
            "pgdata:/var/lib/postgresql/data",
            "./docker/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro",
            "./solar_handoff/db/schema.sql:/docker-init-resources/solar_handoff.sql:ro",
        ])
        entrypoint = [m for m in mounts if m.split(":")[1].startswith(INITDIR)]
        self.assertEqual(entrypoint, [
            "./docker/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro"
        ])
        self.assertFalse(SCHEMA_TARGET.startswith(INITDIR + "/"))
        for mount in mounts:
            if mount.startswith("pgdata:"):
                continue
            self.assertTrue((ROOT / mount.split(":")[0]).is_file())

    def test_init_extension_transaction_and_include_order(self):
        init = (ROOT / "docker/postgres/init.sql").read_text(encoding="utf-8")
        lines = [line.strip() for line in init.splitlines()
                 if line.strip() and not line.strip().startswith("--")]
        self.assertEqual(lines, [
            "CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;",
            "BEGIN;",
            rf"\i {SCHEMA_TARGET}",
            "COMMIT;",
        ])

    def test_existing_schema_is_four_create_statements_only(self):
        schema = (ROOT / "solar_handoff/db/schema.sql").read_text(encoding="utf-8")
        # This simple semicolon split is suitable for the current DDL only, not
        # a general SQL parser: reject unexpected statements rather than skip them.
        uncommented = re.sub(r"--[^\n]*", "", schema)
        statements = [s.strip() for s in uncommented.split(";") if s.strip()]
        self.assertEqual(len(statements), 4)
        self.assertRegex(statements[0], r"(?i)^CREATE\s+SCHEMA\s+solar_handoff$")
        names = []
        for statement in statements[1:]:
            match = re.match(r"(?i)^CREATE\s+TABLE\s+solar_handoff\.(\w+)\s*\(", statement)
            self.assertIsNotNone(match)
            assert match is not None
            names.append(match.group(1))
        self.assertEqual(names, ["chunks", "vectors", "index_info"])
        self.assertRegex(statements[2], r"(?i)public\.vector\s*\(\s*1024\s*\)")
        self.assertNotRegex(uncommented, r"(?i)\b(?:INSERT|COPY|UPDATE|DELETE|COMMIT|ROLLBACK|BEGIN)\b")


if __name__ == "__main__":
    unittest.main()

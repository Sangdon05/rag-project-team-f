"""doc-sync check_docs.py의 의존성 목록 읽기 검사.

정규식으로 읽던 시절 `psycopg[binary,pool]`의 `]`에서 목록이 끊겨 뒤 패키지를 검사하지 못했다.
"""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / ".claude/skills/doc-sync/scripts/check_docs.py"
spec = importlib.util.spec_from_file_location("check_docs", SCRIPT)
assert spec is not None and spec.loader is not None
check_docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_docs)

PYPROJECT = """
[project]
name = "x"
dependencies = [
    "alpha>=1.0",
    "psycopg[binary,pool]>=3.3.9",
    "beta-pkg ; python_version >= '3.13'",
    "Gamma~=2.0",
]

[dependency-groups]
dev = ["httpx>=0.28"]
"""


class DependencyNamesTest(unittest.TestCase):
    def test_reads_packages_after_extras(self):
        self.assertEqual(check_docs.dependency_names(PYPROJECT), ["alpha", "psycopg", "beta-pkg", "gamma"])

    def test_dev_groups_are_not_project_dependencies(self):
        self.assertNotIn("httpx", check_docs.dependency_names(PYPROJECT))

    def test_missing_dependencies_is_empty(self):
        self.assertEqual(check_docs.dependency_names('[project]\nname = "x"\n'), [])

    def test_repo_pyproject_lists_packages_after_psycopg(self):
        names = check_docs.dependency_names((SCRIPT.parents[4] / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertIn("psycopg", names)
        self.assertIn("ragas", names)  # 정규식 방식에서는 빠지던 이름


if __name__ == "__main__":
    unittest.main()

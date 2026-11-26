#!/usr/bin/env python3
"""FastAPI 서비스(api/) 4계층 규칙 자동 검사 (layer-check 스킬).

사용 (저장소 루트에서):
    uv run python .claude/skills/layer-check/scripts/check_layers.py [서비스 경로]   # 기본: api

검사 대상:
  - 슬라이스: 서비스 폴더 바로 아래에서 계층 폴더(domain 등)가 하나라도 있는 폴더
  - 공용 패키지: shared/
  - 서비스 루트 파일: main.py·container.py(조립 지점)를 뺀 나머지 (error_handlers.py 등)
  - tests/, __pycache__/, 숨김 폴더는 검사하지 않는다

위반 (종료 코드 1):
  [구조]     서비스·슬라이스·계층·shared 폴더에 __init__.py 없음
  [의존방향] 계층 간 금지 방향 import (R2)
  [외부의존] 계층별 금지 패키지 import (R1, R8)
  [공용]     domain이 shared.exceptions 밖의 shared 모듈을 import (R1)
  [HTTP예외] domain·application·presentation에서 HTTPException 사용 (R6)
  [CORS]     allow_origins에 "*" 사용 (R13)

경고 (종료 코드에 영향 없음):
  [넓은예외] 전역 핸들러가 ValueError·LookupError·PermissionError·KeyError를 그대로 잡음
  [구조]     계층 폴더 밖에 놓인 슬라이스 파일, 계층 폴더가 없는 패키지

표준 라이브러리만 쓴다. 종료 코드: 0 위반 없음, 1 위반 있음, 2 서비스 폴더 없음.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

LAYERS = ("domain", "infrastructure", "application", "presentation")
SHARED = "shared"
SKIP_DIRS = {"tests", "__pycache__"}
ROOT_EXEMPT_FILES = {"main.py", "container.py"}  # 모든 슬라이스를 조립하는 곳

# RAG 체인·LLM SDK·DB 드라이버·저장소 내부 코드. infrastructure(와 조립 지점)만 import할 수 있다 (R8).
RAG_BOUNDARY = {"langchain", "langgraph", "openai", "tiktoken", "ragas", "pokedex", "psycopg", "sqlalchemy", "scripts"}

FORBIDDEN_LAYERS = {
    "domain": {"infrastructure", "application", "presentation"},
    "infrastructure": {"application", "presentation"},
    "application": {"infrastructure", "presentation"},
    "presentation": {"infrastructure"},
    SHARED: {"infrastructure", "application", "presentation"},
}

FORBIDDEN_PACKAGES = {
    "domain": {"fastapi", "starlette", "pydantic", "uvicorn", "httpx", "dotenv"} | RAG_BOUNDARY,
    "application": {"fastapi", "starlette", "uvicorn"} | RAG_BOUNDARY,
    "infrastructure": {"fastapi", "starlette"},
    "presentation": set(RAG_BOUNDARY),
    SHARED: set(RAG_BOUNDARY),
}

DOMAIN_SHARED_ALLOWED = {"exceptions"}  # domain은 shared 중 순수 예외 모듈만 쓴다
HTTP_EXCEPTION_FORBIDDEN = {"domain", "application", "presentation"}
BROAD_EXCEPTIONS = {"ValueError", "LookupError", "PermissionError", "KeyError", "BaseException"}


def package_hit(top: str, banned: set[str]) -> str | None:
    """`langchain_core`처럼 접두어가 같은 패키지도 잡는다."""
    for name in banned:
        if top == name or top.startswith(name + "_"):
            return name
    return None


def resolve_relative(file_parts: tuple[str, ...], level: int, module: str | None) -> list[str]:
    package = list(file_parts[:-1])
    if level > 1:
        package = package[: len(package) - (level - 1)]
    return package + (module.split(".") if module else [])


def imported_targets(tree: ast.AST, file_parts: tuple[str, ...]) -> list[tuple[int, list[str]]]:
    targets: list[tuple[int, list[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.append((node.lineno, alias.name.split(".")))
        elif isinstance(node, ast.ImportFrom):
            base = resolve_relative(file_parts, node.level, node.module) if node.level else (node.module or "").split(".")
            targets.append((node.lineno, base))
            for alias in node.names:  # `from api.chat import domain` 형태
                targets.append((node.lineno, base + [alias.name]))
    return targets


def handler_exception_name(node: ast.AST) -> str | None:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return None
    if node.func.attr not in ("exception_handler", "add_exception_handler") or not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Name):
        return arg.id
    if isinstance(arg, ast.Attribute):
        return arg.attr
    return None


class Checker:
    def __init__(self, root: Path):
        self.root = root
        self.pkg = root.name  # import 경로의 첫 조각 (예: api)
        self.violations: list[str] = []
        self.warnings: list[str] = []
        self.checked = 0
        self.slices = sorted(
            p.name for p in root.iterdir()
            if p.is_dir() and p.name not in SKIP_DIRS | {SHARED} and not p.name.startswith(".")
            and any((p / layer).is_dir() for layer in LAYERS)
        )

    # ---------- 구조 ----------
    def check_structure(self) -> None:
        if not (self.root / "__init__.py").exists():
            self.violations.append(f"[구조] {self.pkg}/__init__.py 없음")
        for name in self.slices:
            d = self.root / name
            if not (d / "__init__.py").exists():
                self.violations.append(f"[구조] {name}/__init__.py 없음")
            for layer in LAYERS:
                ld = d / layer
                if ld.is_dir() and not (ld / "__init__.py").exists():
                    self.violations.append(f"[구조] {name}/{layer}/__init__.py 없음")
            for py in sorted(d.glob("*.py")):
                if py.name != "__init__.py":
                    self.warnings.append(f"[구조] {name}/{py.name}: 계층 폴더 밖의 파일 (계층 하나에 둔다)")
        shared = self.root / SHARED
        if shared.is_dir() and not (shared / "__init__.py").exists():
            self.violations.append(f"[구조] {SHARED}/__init__.py 없음")
        for p in sorted(self.root.iterdir()):
            if (p.is_dir() and p.name not in SKIP_DIRS | {SHARED} and not p.name.startswith(".")
                    and p.name not in self.slices and any(p.rglob("*.py"))):
                self.warnings.append(f"[구조] {p.name}/: 계층 폴더가 없는 패키지 (슬라이스면 계층 폴더를 만들고, 공용이면 shared/로 옮긴다)")

    # ---------- 파일 ----------
    def iter_targets(self):
        for name in self.slices:
            for layer in LAYERS:
                ld = self.root / name / layer
                if ld.is_dir():
                    for py in sorted(ld.rglob("*.py")):
                        if "__pycache__" not in py.parts:
                            yield py, layer
        shared = self.root / SHARED
        if shared.is_dir():
            for py in sorted(shared.rglob("*.py")):
                if "__pycache__" not in py.parts:
                    yield py, SHARED
        for py in sorted(self.root.glob("*.py")):
            yield py, None if py.name in ROOT_EXEMPT_FILES else SHARED

    def check_file(self, py: Path, role: str | None) -> None:
        rel = py.relative_to(self.root)
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(rel))
        except SyntaxError as err:
            self.violations.append(f"[문법] {rel}:{err.lineno} 파싱 실패: {err.msg}")
            return
        self.checked += 1
        self.check_exception_handlers(tree, rel)
        self.check_cors(tree, rel)
        if role is None:
            return
        self.check_imports(tree, rel, role)
        if role in HTTP_EXCEPTION_FORBIDDEN:
            self.check_http_exception(tree, rel, role)

    def normalize(self, parts: list[str]) -> list[str]:
        """`api.chat.domain` → `chat.domain`. 서비스 패키지 밖이면 그대로 둔다."""
        return parts[1:] if parts and parts[0] == self.pkg else parts

    def check_imports(self, tree: ast.AST, rel: Path, role: str) -> None:
        label = "서비스 루트" if len(rel.parts) == 1 else role
        file_parts = (self.pkg, *rel.parts)
        seen: set[tuple[int, str]] = set()
        for lineno, raw in imported_targets(tree, file_parts):
            if not raw or not raw[0]:
                continue
            internal = raw[0] == self.pkg
            parts = self.normalize(raw)
            if not parts:
                continue
            top = parts[0]
            if not internal:
                hit = package_hit(top, FORBIDDEN_PACKAGES[role])
                if hit and (lineno, top) not in seen:
                    seen.add((lineno, top))
                    self.violations.append(f"[외부의존] {rel}:{lineno} {label} 계층에서 '{top}' import 금지")
                continue
            if top in self.slices and len(parts) > 1 and parts[1] in FORBIDDEN_LAYERS[role]:
                key = (lineno, f"{top}.{parts[1]}")
                if key not in seen:
                    seen.add(key)
                    self.violations.append(f"[의존방향] {rel}:{lineno} {label} → {top}.{parts[1]} 참조 금지")
            if role == "domain" and top == SHARED and len(parts) > 1 and parts[1] not in DOMAIN_SHARED_ALLOWED:
                key = (lineno, f"shared.{parts[1]}")
                if key not in seen:
                    seen.add(key)
                    self.violations.append(f"[공용] {rel}:{lineno} domain → shared.{parts[1]} 참조 금지 (shared.exceptions만 허용)")

    def check_http_exception(self, tree: ast.AST, rel: Path, role: str) -> None:
        lines = sorted({
            n.lineno for n in ast.walk(tree)
            if (isinstance(n, ast.Name) and n.id == "HTTPException")
            or (isinstance(n, ast.Attribute) and n.attr == "HTTPException")
        })
        for lineno in lines:
            self.violations.append(
                f"[HTTP예외] {rel}:{lineno} {role} 계층에서 HTTPException 사용 금지 (도메인 예외를 내고 전역 핸들러에서 변환)"
            )

    def check_exception_handlers(self, tree: ast.AST, rel: Path) -> None:
        for node in ast.walk(tree):
            name = handler_exception_name(node)
            if name in BROAD_EXCEPTIONS:
                self.warnings.append(
                    f"[넓은예외] {rel}:{getattr(node, 'lineno', '?')} 전역 핸들러가 내장 예외 {name}을(를) 그대로 잡음 "
                    f"(라이브러리 버그도 4xx로 숨는다. shared/exceptions.py의 전용 예외를 잡는다)"
                )

    def check_cors(self, tree: ast.AST, rel: Path) -> None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg == "allow_origins" and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                    if any(isinstance(e, ast.Constant) and e.value == "*" for e in kw.value.elts):
                        self.violations.append(f"[CORS] {rel}:{kw.value.lineno} allow_origins에 \"*\" 사용 금지 (환경 변수 목록으로)")

    def run(self) -> int:
        self.check_structure()
        for py, role in self.iter_targets():
            self.check_file(py, role)
        print(f"서비스: {self.pkg}/")
        print(f"검사한 슬라이스: {', '.join(self.slices) or '(없음)'}")
        print(f"검사한 파일: {self.checked}개")
        if self.warnings:
            print(f"\n경고 {len(self.warnings)}건 (종료 코드에 영향 없음)")
            for w in self.warnings:
                print(f"  - {w}")
        if self.violations:
            print(f"\n위반 {len(self.violations)}건")
            for v in self.violations:
                print(f"  - {v}")
            return 1
        print("\n위반 없음")
        return 0


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "api").resolve()
    if not root.is_dir():
        print(f"[오류] 서비스 폴더를 찾을 수 없습니다: {root}")
        return 2
    return Checker(root).run()


if __name__ == "__main__":
    sys.exit(main())

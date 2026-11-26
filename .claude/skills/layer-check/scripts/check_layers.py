#!/usr/bin/env python3
"""4계층(+선택 FSD) 아키텍처 규칙 자동 검사 (layer-check 스킬).

도메인·서비스별 규칙은 이 스크립트에 두지 않는다. 서비스가 프로파일(JSON)로 주입한다.

사용 (저장소 루트에서):
    uv run python .claude/skills/layer-check/scripts/check_layers.py --profile <프로파일.json> [--root <서비스 폴더>]

프로파일 형식은 SKILL.md "프로파일" 절을 본다. --root를 주면 프로파일의 root 대신 쓴다(복사본 검사용).

고정 규칙 (4계층 정의 자체):
  [구조]     서비스 패키지·슬라이스·계층·shared 폴더에 __init__.py 없음
  [의존방향] domain → 다른 계층, application → infrastructure·presentation,
             infrastructure → application·presentation, presentation → infrastructure,
             shared → 슬라이스의 infrastructure·application·presentation

프로파일이 켜는 규칙:
  [외부의존] forbidden_packages: 계층별 금지 패키지 (접두어 일치: sdk → sdk_core)
  [공용]     domain_shared_allowed: domain이 import할 수 있는 shared 모듈
  [HTTP예외] http_exception_forbidden: HTTPException 사용 금지 계층
  [CORS]     cors_wildcard_forbidden: allow_origins에 "*" 금지
  [슬라이스] fsd.cross_slice: 슬라이스 간 import 규칙 (off | warn | error)
  경고 [넓은예외] broad_exception_warn: 전역 핸들러가 잡으면 경고할 내장 예외

종료 코드: 0 위반 없음, 1 위반 있음, 2 프로파일·서비스 폴더 없음.
표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

LAYERS = ("domain", "infrastructure", "application", "presentation")
SHARED_ROLE = "shared"

# 4계층의 정의 자체라 프로파일로 바꾸지 않는다.
FORBIDDEN_LAYERS = {
    "domain": {"infrastructure", "application", "presentation"},
    "infrastructure": {"application", "presentation"},
    "application": {"infrastructure", "presentation"},
    "presentation": {"infrastructure"},
    SHARED_ROLE: {"infrastructure", "application", "presentation"},
}

PROFILE_DEFAULTS = {
    "package": None,               # 기본: root 폴더 이름
    "shared_dirs": ["shared"],
    "skip_dirs": ["tests"],
    "assembly_files": ["main.py", "container.py"],
    "forbidden_packages": {},
    "domain_shared_allowed": None,  # None이면 제한 없음
    "http_exception_forbidden": [],
    "cors_wildcard_forbidden": False,
    "broad_exception_warn": [],
    "fsd": {"cross_slice": "off"},
    "rule_ids": {},
}


def load_profile(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    profile = {**PROFILE_DEFAULTS, **{k: v for k, v in data.items() if not k.startswith("_")}}
    profile["fsd"] = {**PROFILE_DEFAULTS["fsd"], **data.get("fsd", {})}
    if "root" not in profile:
        raise ValueError("프로파일에 root가 없습니다")
    if profile["fsd"]["cross_slice"] not in ("off", "warn", "error"):
        raise ValueError("fsd.cross_slice는 off | warn | error")
    return profile


def package_hit(top: str, banned) -> str | None:
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
            for alias in node.names:  # `from pkg.slice import domain` 형태
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
    def __init__(self, root: Path, profile: dict):
        self.root = root
        self.p = profile
        self.pkg = profile["package"] or root.name
        self.shared = set(profile["shared_dirs"])
        self.skip = set(profile["skip_dirs"]) | {"__pycache__"}
        self.violations: list[str] = []
        self.warnings: list[str] = []
        self.checked = 0
        self.slices = sorted(
            p.name for p in root.iterdir()
            if p.is_dir() and p.name not in self.skip | self.shared and not p.name.startswith(".")
            and any((p / layer).is_dir() for layer in LAYERS)
        )
        if root.name != self.pkg:
            self.warnings.append(
                f"[구조] 폴더 이름({root.name})과 import 패키지({self.pkg})가 다릅니다. "
                f"`{self.pkg}.` 절대 import만 서비스 내부로 판정합니다"
            )

    def tag(self, name: str) -> str:
        rid = self.p["rule_ids"].get(name)
        return f"[{name}{' ' + rid if rid else ''}]"

    # ---------- 구조 ----------
    def check_structure(self) -> None:
        if not (self.root / "__init__.py").exists():
            self.violations.append(f"{self.tag('구조')} {self.root.name}/__init__.py 없음")
        for name in self.slices:
            d = self.root / name
            if not (d / "__init__.py").exists():
                self.violations.append(f"{self.tag('구조')} {name}/__init__.py 없음")
            for layer in LAYERS:
                ld = d / layer
                if ld.is_dir() and not (ld / "__init__.py").exists():
                    self.violations.append(f"{self.tag('구조')} {name}/{layer}/__init__.py 없음")
            for py in sorted(d.glob("*.py")):
                if py.name != "__init__.py":
                    self.warnings.append(f"[구조] {name}/{py.name}: 계층 폴더 밖의 파일")
        for s in sorted(self.shared):
            sd = self.root / s
            if sd.is_dir() and not (sd / "__init__.py").exists():
                self.violations.append(f"{self.tag('구조')} {s}/__init__.py 없음")
        for p in sorted(self.root.iterdir()):
            if (p.is_dir() and p.name not in self.skip | self.shared and not p.name.startswith(".")
                    and p.name not in self.slices and any(p.rglob("*.py"))):
                self.warnings.append(f"[구조] {p.name}/: 계층 폴더가 없는 패키지 (슬라이스면 계층 폴더를, 공용이면 shared로)")

    # ---------- 파일 ----------
    def iter_targets(self):
        for name in self.slices:
            for layer in LAYERS:
                ld = self.root / name / layer
                if ld.is_dir():
                    for py in sorted(ld.rglob("*.py")):
                        if "__pycache__" not in py.parts:
                            yield py, layer, name
        for s in sorted(self.shared):
            sd = self.root / s
            if sd.is_dir():
                for py in sorted(sd.rglob("*.py")):
                    if "__pycache__" not in py.parts:
                        yield py, SHARED_ROLE, None
        for py in sorted(self.root.glob("*.py")):
            yield py, (None if py.name in self.p["assembly_files"] else SHARED_ROLE), None

    def check_file(self, py: Path, role: str | None, slice_name: str | None) -> None:
        rel = py.relative_to(self.root)
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(rel))
        except SyntaxError as err:
            self.violations.append(f"[문법] {rel}:{err.lineno} 파싱 실패: {err.msg}")
            return
        self.checked += 1
        self.check_exception_handlers(tree, rel)
        if self.p["cors_wildcard_forbidden"]:
            self.check_cors(tree, rel)
        if role is None:
            return
        self.check_imports(tree, rel, role, slice_name)
        if role in self.p["http_exception_forbidden"]:
            self.check_http_exception(tree, rel, role)

    def check_imports(self, tree: ast.AST, rel: Path, role: str, slice_name: str | None) -> None:
        label = "서비스 루트" if len(rel.parts) == 1 else role
        banned = self.p["forbidden_packages"].get(role, [])
        seen: set[tuple[int, str]] = set()

        def add(kind: str, lineno: int, key: str, msg: str, warn: bool = False) -> None:
            if (lineno, kind + key) in seen:
                return
            seen.add((lineno, kind + key))
            (self.warnings if warn else self.violations).append(f"{self.tag(kind)} {rel}:{lineno} {msg}")

        for lineno, raw in imported_targets(tree, (self.pkg, *rel.parts)):
            if not raw or not raw[0]:
                continue
            if raw[0] != self.pkg:
                if package_hit(raw[0], banned):
                    add("외부의존", lineno, raw[0], f"{label} 계층에서 '{raw[0]}' import 금지")
                continue
            parts = raw[1:]
            if not parts:
                continue
            top = parts[0]
            if top in self.slices and len(parts) > 1 and parts[1] in FORBIDDEN_LAYERS[role]:
                add("의존방향", lineno, f"{top}.{parts[1]}", f"{label} → {top}.{parts[1]} 참조 금지")
            allowed = self.p["domain_shared_allowed"]
            if role == "domain" and top in self.shared and allowed is not None and len(parts) > 1 and parts[1] not in allowed:
                add("공용", lineno, f"{top}.{parts[1]}", f"domain → {top}.{parts[1]} 참조 금지 (허용: {', '.join(allowed) or '없음'})")
            mode = self.p["fsd"]["cross_slice"]
            if mode == "off":
                continue
            if slice_name and top in self.slices and top != slice_name and len(parts) > 1 and parts[1] in LAYERS:
                add("슬라이스", lineno, top, f"{slice_name} → {top}.{parts[1]}: 다른 슬라이스는 공개 API(`{self.pkg}.{top}`)로만 참조",
                    warn=(mode == "warn"))
            if role == SHARED_ROLE and len(rel.parts) > 1 and top in self.slices:
                add("슬라이스", lineno, top, f"shared → {top}: shared는 슬라이스를 참조하지 않는다", warn=(mode == "warn"))

    def check_http_exception(self, tree: ast.AST, rel: Path, role: str) -> None:
        lines = sorted({
            n.lineno for n in ast.walk(tree)
            if (isinstance(n, ast.Name) and n.id == "HTTPException")
            or (isinstance(n, ast.Attribute) and n.attr == "HTTPException")
        })
        for lineno in lines:
            self.violations.append(f"{self.tag('HTTP예외')} {rel}:{lineno} {role} 계층에서 HTTPException 사용 금지 (도메인 예외 → 전역 핸들러)")

    def check_exception_handlers(self, tree: ast.AST, rel: Path) -> None:
        for node in ast.walk(tree):
            name = handler_exception_name(node)
            if name and name in self.p["broad_exception_warn"]:
                self.warnings.append(
                    f"[넓은예외] {rel}:{getattr(node, 'lineno', '?')} 전역 핸들러가 내장 예외 {name}을(를) 그대로 잡음 (전용 예외 권장)"
                )

    def check_cors(self, tree: ast.AST, rel: Path) -> None:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg == "allow_origins" and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                    if any(isinstance(e, ast.Constant) and e.value == "*" for e in kw.value.elts):
                        self.violations.append(f"{self.tag('CORS')} {rel}:{node.lineno} allow_origins에 \"*\" 사용 금지")

    def run(self) -> int:
        self.check_structure()
        for py, role, slice_name in self.iter_targets():
            self.check_file(py, role, slice_name)
        print(f"서비스: {self.root.name}/ (import 패키지 {self.pkg}, FSD 슬라이스 규칙 {self.p['fsd']['cross_slice']})")
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
    ap = argparse.ArgumentParser(description="4계층(+선택 FSD) 아키텍처 규칙 자동 검사")
    ap.add_argument("--profile", required=True, help="서비스 규칙 프로파일 JSON")
    ap.add_argument("--root", help="서비스 폴더 (기본: 프로파일의 root, 저장소 루트 기준)")
    args = ap.parse_args()
    profile_path = Path(args.profile)
    if not profile_path.is_file():
        print(f"[오류] 프로파일을 찾을 수 없습니다: {profile_path}")
        return 2
    try:
        profile = load_profile(profile_path)
    except (ValueError, json.JSONDecodeError) as err:
        print(f"[오류] 프로파일 형식: {err}")
        return 2
    root = Path(args.root or profile["root"]).resolve()
    if not root.is_dir():
        print(f"[오류] 서비스 폴더를 찾을 수 없습니다: {root}")
        return 2
    return Checker(root, profile).run()


if __name__ == "__main__":
    sys.exit(main())

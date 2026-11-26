"""spec-plan 스킬의 workdocs.py: 생성·승인(HITL 게이트)·병렬 단계·완료 판정·보관 흐름.

임시 git 저장소에서 스크립트를 실제 명령으로 실행한다. 저장소 문서는 건드리지 않는다.
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".claude" / "skills" / "spec-plan" / "scripts" / "workdocs.py"
TODAY = "2026-11-26"

SPEC_BODY = """
# 예시 스펙

## 3. 요구사항

| ID | 요구사항 | 구분 |
| --- | --- | --- |
| REQ-1 | 청크 계약 파일이 있다 | 필수 |
| REQ-2 | 문서가 동기화된다 | 필수 |

## 6. 완료 기준

| ID | 기준 | 확인 방법 | 기대 결과 | 요구사항 |
| --- | --- | --- | --- | --- |
| AC-1 | 계약 파일 검증 | 명령: `validate_contract.py` | exit 0 | REQ-1 |
| AC-2 | doc-sync 통과 | 명령: `check_docs.py --strict` | ERROR 0 | REQ-2 |

## 7. 미결 사항

| ID | 질문 | 선택지·기본값 | 결정 | 상태 |
| --- | --- | --- | --- | --- |
| Q-1 | 형식은? | JSON(기본) | {decision} | {qstate} |

## 8. 결정 기록

| 날짜 | 결정 | 결정자 | 근거 |
| --- | --- | --- | --- |
| 2026-11-26 | 스펙 승인 | user | 채팅 확인 |
{decisions}
"""

PLAN_BODY = """
# 예시 계획

- 스펙: [{spec}](../specs/{spec}.md)

## 2. 작업 분해

| ID | 작업 | 담당 | 선행 | 산출물 | 완료 기준 | 상태 |
| --- | --- | --- | --- | --- | --- | --- |
{tasks}

## 8. 결정 기록

| 날짜 | 결정 | 결정자 | 근거 |
| --- | --- | --- | --- |
| 2026-11-26 | 계획 승인 | user | 채팅 확인 |

## 9. 완료 판정

| AC | 결과 | 근거 | 확인자 |
| --- | --- | --- | --- |
{verdict}
"""


def fm(**kv) -> str:
    return "---\n" + "\n".join(f"{k}: {v}".rstrip() for k, v in kv.items()) + "\n---\n"


class WorkDocsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        (self.root / ".claude" / "agents").mkdir(parents=True)
        for a in ("data-engineer", "rag-developer"):
            (self.root / ".claude" / "agents" / f"{a}.md").write_text(
                "---\nname: x\ntools: Read, Write, Edit, Bash\n---\n", encoding="utf-8")
        (self.root / ".claude" / "agents" / "api-reviewer.md").write_text(
            "---\nname: api-reviewer\ntools: Read, Grep, Glob, Bash\n---\n", encoding="utf-8")
        self.git("init", "-q")
        self.git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def run_wd(self, *args):
        env = {**os.environ, "WORKDOCS_ROOT": str(self.root), "WORKDOCS_TODAY": TODAY}
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.root, env=env,
                              capture_output=True, text=True)

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def write(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    # 픽스처 ------------------------------------------------------------
    spec_id = f"{TODAY}-sample"
    plan_id = f"{TODAY}-sample"

    def write_spec(self, status="clarifying", qstate="resolved", decisions="", approved=False, ac2="AC-2"):
        head = fm(type="spec", id=self.spec_id, title="예시", status="clarifying", owner="orchestrator",
                  created=TODAY, updated=TODAY, approved_by="", approved_at="", approved_hash="",
                  completed_at="", archived_at="", related="[]")
        body = SPEC_BODY.format(decision="JSON" if qstate == "resolved" else "", qstate=qstate,
                                decisions=decisions).replace("| AC-2 |", f"| {ac2} |")
        self.write(f"docs/specs/{self.spec_id}.md", head + body)
        if approved or status == "approved":
            r = self.run_wd("approve", "spec", self.spec_id, "--by", "user")
            assert r.returncode == 0, r.stdout + r.stderr

    def write_plan(self, tasks, verdict=(), status="approved"):
        head = fm(type="plan", id=self.plan_id, title="예시 계획", status="draft", owner="orchestrator",
                  spec=self.spec_id, created=TODAY, updated=TODAY, approved_by="", approved_at="",
                  approved_hash="", completed_at="", archived_at="", base_commit="abc1234")
        self.write(f"docs/plans/{self.plan_id}.md",
                   head + PLAN_BODY.format(spec=self.spec_id, tasks="\n".join(tasks), verdict="\n".join(verdict)))
        if status != "draft":
            r = self.run_wd("approve", "plan", self.plan_id, "--by", "user")
            if r.returncode != 0:
                return r
        if status == "in_progress":
            self.run_wd("start", self.plan_id)
        return None

    GOOD_TASKS = [
        "| T-1 | 계약 작성 | data-engineer | - | `contracts/` | AC-1 | done |",
        "| T-2 | 문서 갱신 | rag-developer | - | `docs/references/` | AC-2 | done |",
        "| T-3 | 리뷰 | api-reviewer | T-1, T-2 | `docs/reviews/` | 지원: APPROVE | done |",
    ]
    GOOD_VERDICT = [
        "| AC-1 | pass | exit 0 | 오케스트레이터 |",
        "| AC-2 | pass | ERROR 0 | api-reviewer |",
    ]

    # 테스트 ------------------------------------------------------------
    def test_new_spec_uses_name_rule_and_updates_index(self):
        r = self.run_wd("new", "spec", "sample", "--title", "예시")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self.read(f"docs/specs/{TODAY}-sample.md")
        self.assertIn(f"id: {TODAY}-sample", text)
        self.assertIn("status: draft", text)
        self.assertIn(f"[{TODAY}-sample]({TODAY}-sample.md)", self.read("docs/specs/README.md"))
        self.assertEqual(self.run_wd("check").returncode, 0)
        bad = self.run_wd("new", "spec", "Health_API", "--title", "x")
        self.assertNotEqual(bad.returncode, 0)

    def test_plan_requires_approved_spec(self):
        self.run_wd("new", "spec", "sample", "--title", "예시")
        r = self.run_wd("new", "plan", "sample", "--spec", self.spec_id, "--title", "계획")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("approved가 아님", r.stderr)

    def test_approve_refuses_open_question_and_restores_file(self):
        self.write_spec(qstate="open")
        before = self.read(f"docs/specs/{self.spec_id}.md")
        r = self.run_wd("approve", "spec", self.spec_id, "--by", "user")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Q-1", r.stdout)
        self.assertEqual(self.read(f"docs/specs/{self.spec_id}.md"), before)

    def test_approve_then_plan_from_template(self):
        self.write_spec()
        r = self.run_wd("approve", "spec", self.spec_id, "--by", "user")
        self.assertEqual(r.returncode, 0, r.stdout)
        text = self.read(f"docs/specs/{self.spec_id}.md")
        self.assertIn("status: approved", text)
        self.assertIn("approved_by: user", text)
        r = self.run_wd("new", "plan", "sample", "--spec", self.spec_id, "--title", "계획")
        self.assertEqual(r.returncode, 0, r.stderr)
        plan = self.read(f"docs/plans/{self.plan_id}.md")
        self.assertIn(f"spec: {self.spec_id}", plan)
        self.assertIn(f"[{self.spec_id}](../specs/{self.spec_id}.md)", plan)

    def test_waves_and_parallel_output_conflict(self):
        self.write_spec(status="approved", approved=True)
        self.write_plan(self.GOOD_TASKS[:2] + [self.GOOD_TASKS[2].replace("done", "todo")])
        r = self.run_wd("waves", self.plan_id)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("단계 1: T-1(data-engineer), T-2(rag-developer)", r.stdout)
        self.assertIn("단계 2: T-3(api-reviewer)", r.stdout)
        clash = [self.GOOD_TASKS[0], "| T-2 | 문서 | rag-developer | - | `contracts/chunk_schema.json` | AC-2 | todo |"]
        self.write_plan(clash)
        r = self.run_wd("check")
        self.assertIn("같은 산출물", r.stdout)

    def test_plan_errors_cycle_unknown_assignee_missing_ac(self):
        self.write_spec(status="approved", approved=True)
        self.write_plan([
            "| T-1 | a | data-engineer | T-2 | `a/` | AC-1 | todo |",
            "| T-2 | b | 누군가 | T-1 | `b/` | AC-9 | todo |",
        ])
        out = self.run_wd("check").stdout
        self.assertIn("순환", out)
        self.assertIn("'누군가'", out)
        self.assertIn("없는 AC-9", out)
        self.assertIn("AC-2", out)  # 맡은 작업 없음

    def test_archive_refuses_until_criteria_met(self):
        self.write_spec(status="approved", approved=True)
        self.write_plan([self.GOOD_TASKS[0].replace("done", "doing")] + self.GOOD_TASKS[1:],
                        ["| AC-1 | fail | | |", self.GOOD_VERDICT[1]], status="in_progress")
        r = self.run_wd("archive", self.spec_id)
        self.assertEqual(r.returncode, 1)
        self.assertIn("T-1 상태가 doing", r.stdout)
        self.assertIn("AC-1 결과 'fail'", r.stdout)
        self.assertTrue((self.root / f"docs/specs/{self.spec_id}.md").exists())
        self.assertIn("status: approved", self.read(f"docs/specs/{self.spec_id}.md"))

    def test_confirmer_must_not_be_assignee(self):
        self.write_spec(status="approved", approved=True)
        self.write_plan(self.GOOD_TASKS, ["| AC-1 | pass | 200 | data-engineer |", self.GOOD_VERDICT[1]],
                        status="in_progress")
        r = self.run_wd("archive", self.spec_id)
        self.assertEqual(r.returncode, 1)
        self.assertIn("수행 담당 'data-engineer'", r.stdout)

    def test_waived_needs_user_decision(self):
        self.write_spec(status="approved", approved=True)
        verdict = ["| AC-1 | waived | 범위 제외 | 사용자 |", self.GOOD_VERDICT[1]]
        self.write_plan(self.GOOD_TASKS, verdict, status="in_progress")
        self.assertIn("사람(결정자)의 결정이 없음", self.run_wd("archive", self.spec_id).stdout)
        self.write_spec(status="approved", approved=True,
                        decisions=f"| {TODAY} | AC-1 이번 범위 제외 | 사용자 | 일정 |")
        self.assertEqual(self.run_wd("archive", self.spec_id, "--dry-run").returncode, 0)

    def test_archive_moves_sets_frontmatter_and_relinks(self):
        self.write_spec(status="approved", approved=True)
        self.write_plan(self.GOOD_TASKS, self.GOOD_VERDICT, status="in_progress")
        self.write("docs/notes.md", f"[스펙](specs/{self.spec_id}.md#6-완료-기준), [계획](plans/{self.plan_id}.md)\n")
        self.git("add", "-A")
        self.run_wd("index")
        r = self.run_wd("archive", self.spec_id)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        spec = self.read(f"docs/archives/specs/{self.spec_id}.md")
        plan = self.read(f"docs/archives/plans/{self.plan_id}.md")
        for text in (spec, plan):
            self.assertIn("status: done", text)
            self.assertIn(f"completed_at: {TODAY}", text)
            self.assertIn(f"archived_at: {TODAY}", text)
        self.assertFalse((self.root / f"docs/specs/{self.spec_id}.md").exists())
        self.assertIn(f"[{self.spec_id}](../specs/{self.spec_id}.md)", plan)
        notes = self.read("docs/notes.md")
        self.assertIn(f"archives/specs/{self.spec_id}.md#6-완료-기준", notes)
        self.assertIn(f"archives/plans/{self.plan_id}.md", notes)
        self.assertIn(f"specs/{self.spec_id}.md", self.read("docs/archives/README.md"))
        self.assertNotIn(self.spec_id, self.read("docs/specs/README.md"))
        r = self.run_wd("check", "--strict")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_cancel_spec_cascades_to_plans(self):
        self.write_spec(status="approved", approved=True)
        self.write_plan([t.replace("done", "todo") for t in self.GOOD_TASKS])
        r = self.run_wd("cancel", "spec", self.spec_id, "--reason", "우선순위 변경")
        self.assertIn("사용자 결정이 필요", r.stderr)
        self.write_spec(status="approved", decisions=f"| {TODAY} | 스펙 취소 | user | 우선순위 |")
        self.write_plan([t.replace("done", "todo") for t in self.GOOD_TASKS])
        r = self.run_wd("cancel", "spec", self.spec_id, "--reason", "우선순위 변경")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for rel in (f"docs/archives/specs/{self.spec_id}.md", f"docs/archives/plans/{self.plan_id}.md"):
            text = self.read(rel)
            self.assertIn("status: cancelled", text)
            self.assertIn("cancel_reason: 우선순위 변경", text)
        self.assertEqual(self.run_wd("check").returncode, 0)

    def test_location_and_name_rules(self):
        self.write("docs/specs/sample.md", fm(type="spec", id="sample", status="done"))
        out = self.run_wd("check").stdout
        self.assertIn("[name]", out)
        self.assertIn("보관해야 함", out)
        self.assertRegex(out, re.compile(r"'created' 없음"))

    # 행동 시뮬레이션에서 나온 우회 경로 ----------------------------------
    def test_escaped_pipe_in_cell_keeps_columns(self):
        self.write_spec()
        p = self.root / f"docs/specs/{self.spec_id}.md"
        p.write_text(p.read_text(encoding="utf-8").replace(
            "명령: `check_docs.py --strict`", "명령: `grep -E \"a\\|b\" x`"), encoding="utf-8")
        r = self.run_wd("approve", "spec", self.spec_id, "--by", "user")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_approve_needs_person_and_decision_row(self):
        self.write_spec()
        r = self.run_wd("approve", "spec", self.spec_id, "--by", "api-reviewer")
        self.assertIn("사람이 아님", r.stderr)
        r = self.run_wd("approve", "spec", self.spec_id, "--by", "sangdon")
        self.assertIn("승인 행이 없음", r.stderr)
        self.run_wd("approve", "spec", self.spec_id, "--by", "user")
        r = self.run_wd("approve", "spec", self.spec_id, "--by", "user")
        self.assertIn("clarifying으로 되돌리고", r.stderr)

    def test_editing_ac_after_approval_blocks_archive(self):
        self.write_spec(status="approved")
        self.write_plan(self.GOOD_TASKS, self.GOOD_VERDICT, status="in_progress")
        p = self.root / f"docs/specs/{self.spec_id}.md"
        text = p.read_text(encoding="utf-8")
        p.write_text("\n".join(l for l in text.splitlines() if not l.startswith("| AC-2 ")) + "\n",
                     encoding="utf-8")
        r = self.run_wd("archive", self.spec_id, "--dry-run")
        self.assertEqual(r.returncode, 1)
        self.assertIn("approved_hash 불일치", r.stdout)

    def test_cancelled_task_does_not_drop_its_ac(self):
        self.write_spec(status="approved")
        tasks = [self.GOOD_TASKS[0], self.GOOD_TASKS[1].replace("| done |", "| cancelled |"), self.GOOD_TASKS[2]]
        self.write_plan(tasks, self.GOOD_VERDICT[:1], status="in_progress")
        r = self.run_wd("archive", self.spec_id, "--dry-run")
        self.assertIn("완료 판정 표에 AC-2가 없음", r.stdout)

    def test_confirmer_suffix_and_orchestrator_rules(self):
        self.write_spec(status="approved")
        tasks = [self.GOOD_TASKS[0], self.GOOD_TASKS[1].replace("rag-developer", "오케스트레이터"), self.GOOD_TASKS[2]]
        verdict = ["| AC-1 | pass | 200 | data-engineer (보고 기준) |", "| AC-2 | pass | ERROR 0 | 오케스트레이터 |"]
        self.write_plan(tasks, verdict, status="in_progress")
        out = self.run_wd("archive", self.spec_id, "--dry-run").stdout
        self.assertIn("AC-1 확인자", out)
        self.assertNotIn("AC-2 확인자", out)  # 명령: AC는 오케스트레이터가 다시 실행해 확인 가능

    def test_waived_matches_exact_ac_id(self):
        self.write_spec(status="approved", decisions=f"| {TODAY} | AC-10 범위 제외 | user | x |")
        verdict = ["| AC-1 | waived | 범위 제외 | user |", self.GOOD_VERDICT[1]]
        self.write_plan(self.GOOD_TASKS, verdict, status="in_progress")
        self.assertIn("AC-1 waived", self.run_wd("archive", self.spec_id, "--dry-run").stdout)

    def test_archived_doc_edit_detected_and_no_warn_for_readonly(self):
        self.write_spec(status="approved")
        tasks = self.GOOD_TASKS[:2] + ["| T-3 | 리뷰 | api-reviewer | T-1, T-2 | - | 지원: APPROVE | done |"]
        self.write_plan(tasks, self.GOOD_VERDICT, status="in_progress")
        self.assertNotIn("산출물 경로가 없음", self.run_wd("check").stdout)
        self.assertEqual(self.run_wd("archive", self.spec_id).returncode, 0)
        self.assertEqual(self.run_wd("check", "--strict").returncode, 0)
        p = self.root / f"docs/archives/specs/{self.spec_id}.md"
        p.write_text(p.read_text(encoding="utf-8").replace("청크 계약 파일이", "청크 계약 파일은"), encoding="utf-8")
        r = self.run_wd("check")
        self.assertIn("archived_hash 불일치", r.stdout)

    def test_plan_is_director_judgement_without_hitl(self):
        self.write_spec(status="approved")
        self.write_plan(self.GOOD_TASKS, status="draft")
        r = self.run_wd("approve", "plan", self.plan_id, "--by", "data-engineer")
        self.assertIn("하위 에이전트", r.stderr)
        r = self.run_wd("approve", "plan", self.plan_id)  # 결정 행·사용자 없이 디렉터 확정
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("approved_by: 오케스트레이터", self.read(f"docs/plans/{self.plan_id}.md"))
        self.assertIn("--by <사용자>", self.run_wd("approve", "spec", self.spec_id).stderr)
        r = self.run_wd("cancel", "plan", self.plan_id, "--reason", "작업 재구성")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("status: approved", self.read(f"docs/specs/{self.spec_id}.md"))

    def test_start_requires_approved_plan(self):
        self.write_spec(status="approved")
        self.write_plan(self.GOOD_TASKS, status="draft")
        self.assertIn("사용자 승인", self.run_wd("start", self.plan_id).stderr)


if __name__ == "__main__":
    unittest.main()

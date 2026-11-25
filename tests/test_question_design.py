"""Question-only packet boundaries; no model, database, or eval-set access.

The fixtures exercise structure and provenance, not semantic equivalence or
the quality of generated prose. All source mutations stay in memory.
"""

import copy
import hashlib
import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".claude" / "skills" / "question-design" / "scripts" / "question_packets.py"
SOURCE = ROOT / "docs" / "problem.md"


def load_module():
    spec = importlib.util.spec_from_file_location("question_packets_under_test", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load question packet helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QuestionPacketSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.packet = cls.mod.build_packet(cls.source)

    def test_real_source_provides_only_planning_inputs(self):
        packet = self.packet
        self.assertEqual([p["persona_id"] for p in packet["personas"]], ["P1", "P2", "P3"])
        self.assertEqual(
            {s["seed_id"] for s in packet["seeds"]},
            {f"P{persona}-{number:02}" for persona in (1, 2, 3) for number in (1, 2, 3)},
        )
        self.assertEqual(len(packet["seeds"]), 9)
        self.assertEqual(packet["scope"]["game"], "Red/Blue")
        self.assertEqual(packet["source"], "docs/problem.md")
        self.assertEqual(
            packet["source_sha256"], hashlib.sha256(self.source.encode("utf-8")).hexdigest()
        )
        for seed in packet["seeds"]:
            self.assertEqual(set(seed), {"seed_id", "persona_id", "scenario_id", "question"})

    def test_answer_fact_evidence_and_plan_canaries_are_not_extracted(self):
        # Change each forbidden row class in the real document independently.
        # Only provenance may change; no canary or adjacent answer table may leak.
        for label in (
            "답변 예시", "필수 확인 사실·조건", "근거 위치", "오답·실패 기준", "처리 계획"
        ):
            with self.subTest(row=label):
                marker = "DO_NOT_EXTRACT_ANSWER_CANARY"
                pattern = rf"(?m)^(\| {re.escape(label)} \|)[^\n]*$"
                mutated, replacements = re.subn(
                    pattern, lambda match: f"{match.group(1)} {marker} |", self.source
                )
                self.assertGreater(replacements, 0, "Source row contract disappeared")
                actual = self.mod.build_packet(mutated)
                self.assertNotIn(marker, json.dumps(actual, ensure_ascii=False))
                expected = copy.deepcopy(self.packet)
                expected.pop("source_sha256")
                actual.pop("source_sha256")
                self.assertEqual(actual, expected)

    def test_missing_or_duplicate_seed_heading_fails_closed(self):
        for seed_id in ("P1-01", "P2-02", "P3-03"):
            heading = f"### {seed_id}"
            self.assertIn(heading + "\n", self.source)
            variants = {
                "missing": self.source.replace(heading + "\n", heading + " removed\n", 1),
                "duplicate": self.source + f"\n{heading}\n> duplicate input\n",
            }
            for kind, mutated in variants.items():
                with self.subTest(seed=seed_id, mutation=kind):
                    with self.assertRaises(ValueError):
                        self.mod.build_packet(mutated)

    def test_missing_or_duplicate_persona_section_fails_closed(self):
        heading = "## 2. 사용자 페르소나"
        variants = (
            self.source.replace(heading, heading + " removed", 1),
            self.source + f"\n{heading}\n",
        )
        for mutated in variants:
            with self.subTest(duplicate=mutated.endswith(heading + "\n")):
                with self.assertRaises(ValueError):
                    self.mod.build_packet(mutated)

    def test_missing_persona_column_fails_closed(self):
        # Remove P2 from the actual persona table header, not from a synthetic copy.
        pattern = r"(?m)^(\| 항목 \| P1[^|]*\|)[^|]*\|([^\n]*)$"
        mutated, replacements = re.subn(pattern, r"\1\2", self.source, count=1)
        self.assertEqual(replacements, 1)
        with self.assertRaises(ValueError):
            self.mod.build_packet(mutated)

    def test_missing_profile_row_fails_closed(self):
        mutated, replacements = re.subn(
            r"(?m)^\| 이미 아는 것 \|[^\n]*\n?", "", self.source, count=1
        )
        self.assertEqual(replacements, 1)
        with self.assertRaises(ValueError):
            self.mod.build_packet(mutated)

    def test_empty_persona_profile_fails_closed(self):
        start = self.source.index("## 2. 사용자 페르소나")
        end = self.source.index("\n## ", start + 1)
        persona_section = self.source[start:end]
        removed = []
        changed_lines = []
        for line in persona_section.splitlines():
            if line.startswith("|"):
                cells = line.split("|")
                label = cells[1].strip()
                if label != "항목" and not re.fullmatch(r"[-: ]+", label):
                    removed.append(cells[3].strip())
                    cells[3] = " "  # Keep the column while removing P2's actual profile.
                    line = "|".join(cells)
            changed_lines.append(line)
        self.assertGreaterEqual(len(removed), 8)
        self.assertTrue(all(removed))
        mutated = self.source[:start] + "\n".join(changed_lines) + self.source[end:]
        with self.assertRaises(ValueError):
            self.mod.build_packet(mutated)

    def test_changed_source_game_fails_closed(self):
        original = "Red/Blue, 싱글 배틀 전 준비"
        self.assertIn(original, self.source)
        with self.assertRaises(ValueError):
            self.mod.build_packet(self.source.replace(original, "Yellow, 싱글 배틀 전 준비", 1))

    def test_s01_b_keeps_its_explicit_source_override(self):
        seed = next(s for s in self.packet["seeds"] if s["seed_id"] == "P3-02")
        self.assertEqual(seed["scenario_id"], "S01-B")
        scenario = self.packet["scenarios"]["S01-B"]
        self.assertEqual(scenario["base_scenario"], "S01")
        card_match = re.search(r"(?ms)^### P3-02\n(.*?)(?=^### |^## |\Z)", self.source)
        self.assertIsNotNone(card_match)
        condition_match = re.search(
            r"(?m)^\| 상황·추가 확인 \| (.*?) \|$", card_match.group(1)
        )
        self.assertIsNotNone(condition_match)
        self.assertEqual(scenario["changed_input"], condition_match.group(1))
        self.assertTrue(scenario["changed_input"].startswith("S01-B:"))
        other_seeds = [s for s in self.packet["seeds"] if s["seed_id"] != "P3-02"]
        self.assertTrue(all(s["scenario_id"] == "S01" for s in other_seeds))

    def test_missing_s01_b_input_fails_closed(self):
        self.assertIn("S01-B:", self.source)
        with self.assertRaises(ValueError):
            self.mod.build_packet(self.source.replace("S01-B:", "unspecified scenario:", 1))


class QuestionCandidateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.packet = cls.mod.build_packet(cls.source)
        cls.seeds = {s["seed_id"]: s for s in cls.packet["seeds"]}

    def candidate(self, seed_id="P1-01", candidate_id="Q01"):
        seed = self.seeds[seed_id]
        return {
            "candidate_id": candidate_id,
            "seed_id": seed_id,
            "persona_id": seed["persona_id"],
            "scenario_id": seed["scenario_id"],
            "information_need_id": seed_id,
            "relation": "paraphrase",
            # An opaque fixture for structural validation, not a prose-quality oracle.
            "question": f"조건을 유지해 묻습니다: {seed['question']}",
            "changed_conditions": [],
            "missing_inputs": [],
            "review_status": "draft",
        }

    def output(self, *items):
        return {
            "schema_version": self.packet["schema_version"],
            "source_sha256": self.packet["source_sha256"],
            "candidates": list(items) if items else [self.candidate()],
        }

    def test_valid_drafts_leave_meaning_and_answerability_pending(self):
        items = [self.candidate(seed_id, f"Q{number:02}")
                 for number, seed_id in enumerate(("P1-01", "P2-01", "P3-01"), 1)]
        result = self.mod.check_candidates(self.packet, self.output(*items))
        self.assertEqual(result["structural_check"], "pass")
        self.assertEqual(result["candidate_count"], 3)
        self.assertEqual(result["persona_counts"], {"P1": 1, "P2": 1, "P3": 1})
        self.assertEqual(result["meaning_review"], "pending")
        self.assertEqual(result["answerability_review"], "pending")
        self.assertIs(result["official_evalset"], False)

    def test_original_numeric_question_premise_is_allowed(self):
        seed = self.seeds["P3-03"]
        self.assertRegex(seed["question"], r"\d")
        item = self.candidate("P3-03")
        self.assertIn(seed["question"], item["question"])
        self.assertEqual(
            self.mod.check_candidates(self.packet, self.output(item))["structural_check"], "pass"
        )

    def test_answer_or_evidence_fields_are_rejected_at_both_levels(self):
        for field in ("answer", "expected_answer", "key_facts", "allowed_evidence", "no_evidence_reason"):
            for level in ("output", "candidate"):
                with self.subTest(field=field, level=level):
                    output = self.output()
                    target = output if level == "output" else output["candidates"][0]
                    target[field] = "FORBIDDEN_ANSWER_PAYLOAD"
                    with self.assertRaises(ValueError):
                        self.mod.check_candidates(self.packet, output)

    def test_wrong_persona_is_rejected(self):
        for persona in ("P2", "P4"):
            with self.subTest(persona=persona):
                item = self.candidate("P1-01")
                item["persona_id"] = persona
                with self.assertRaises(ValueError):
                    self.mod.check_candidates(self.packet, self.output(item))

    def test_paraphrase_cannot_change_scenario(self):
        for seed_id, scenario in (("P1-01", "S01-B"), ("P3-02", "S01"), ("P1-01", "S99")):
            with self.subTest(seed=seed_id, scenario=scenario):
                item = self.candidate(seed_id)
                item["scenario_id"] = scenario
                with self.assertRaises(ValueError):
                    self.mod.check_candidates(self.packet, self.output(item))

    def test_only_draft_review_status_is_allowed(self):
        for status in ("approved", "final", "answerable", ""):
            with self.subTest(status=status):
                item = self.candidate()
                item["review_status"] = status
                with self.assertRaises(ValueError):
                    self.mod.check_candidates(self.packet, self.output(item))

    def test_condition_change_must_be_explicit(self):
        item = self.candidate("P1-02")
        item.update(relation="condition_change", scenario_id="S01-B")
        with self.assertRaises(ValueError):
            self.mod.check_candidates(self.packet, self.output(item))
        item["changed_conditions"] = ["현재 기술: 물대포 포함 -> 물대포 제외"]
        self.assertEqual(
            self.mod.check_candidates(self.packet, self.output(item))["structural_check"], "pass"
        )

    def test_other_relations_cannot_silently_change_conditions(self):
        for relation in ("paraphrase", "new_need"):
            with self.subTest(relation=relation):
                item = self.candidate()
                item.update(relation=relation, changed_conditions=["레벨: 20 -> 25"])
                if relation == "new_need":
                    item["information_need_id"] = "N-EXTRA"
                with self.assertRaises(ValueError):
                    self.mod.check_candidates(self.packet, self.output(item))

    def test_new_need_requires_its_own_identifier(self):
        item = self.candidate("P2-02")
        item.update(relation="new_need", information_need_id="N-EXTRA")
        self.assertEqual(
            self.mod.check_candidates(self.packet, self.output(item))["structural_check"], "pass"
        )
        for need_id in ("P2-02", "N-", "N-lowercase", "D01"):
            with self.subTest(need_id=need_id):
                item["information_need_id"] = need_id
                with self.assertRaises(ValueError):
                    self.mod.check_candidates(self.packet, self.output(item))

    def test_paraphrase_and_condition_change_keep_seed_need_id(self):
        for relation in ("paraphrase", "condition_change"):
            with self.subTest(relation=relation):
                item = self.candidate()
                item.update(relation=relation, information_need_id="N-UNRELATED")
                if relation == "condition_change":
                    item["changed_conditions"] = ["레벨: 20 -> 25"]
                with self.assertRaises(ValueError):
                    self.mod.check_candidates(self.packet, self.output(item))

    def test_duplicate_candidate_ids_are_rejected(self):
        first, second = self.candidate(), self.candidate("P2-01")
        with self.assertRaises(ValueError):
            self.mod.check_candidates(self.packet, self.output(first, second))

    def test_normalized_duplicate_questions_are_rejected(self):
        first = self.candidate()
        second = self.candidate(candidate_id="Q02")
        second["question"] = "\n  ".join(first["question"].split())
        with self.assertRaises(ValueError):
            self.mod.check_candidates(self.packet, self.output(first, second))

    def test_verbatim_seed_is_not_a_new_candidate(self):
        item = self.candidate()
        item["question"] = "  " + self.seeds[item["seed_id"]]["question"] + "\n"
        with self.assertRaises(ValueError):
            self.mod.check_candidates(self.packet, self.output(item))

    def test_stale_source_hash_is_rejected(self):
        output = self.output()
        output["source_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.mod.check_candidates(self.packet, output)
        # Even an answer-row-only edit invalidates previously generated candidates.
        current_packet = self.mod.build_packet(self.source + "\n")
        with self.assertRaises(ValueError):
            self.mod.check_candidates(current_packet, self.output())

    def test_invalid_collections_ids_and_array_types_are_rejected(self):
        for value in ([], None, {}, "not-an-array"):
            with self.subTest(candidates=value):
                output = self.output()
                output["candidates"] = value
                with self.assertRaises(ValueError):
                    self.mod.check_candidates(self.packet, output)
        for field, value in (
            ("candidate_id", "D01"), ("seed_id", "P9-99"),
            ("changed_conditions", "hidden condition"), ("missing_inputs", [""]),
            ("missing_inputs", [{"answer": "not permitted"}]),
        ):
            with self.subTest(field=field, value=value):
                item = self.candidate()
                item[field] = value
                with self.assertRaises(ValueError):
                    self.mod.check_candidates(self.packet, self.output(item))


class QuestionRunPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_relative_and_absolute_batch_paths_are_allowed(self):
        expected = (ROOT / "runs" / "question-design" / "batch" / "candidates.json").resolve()
        self.assertEqual(self.mod.run_path("runs/question-design/batch/candidates.json"), expected)
        self.assertEqual(self.mod.run_path(str(expected)), expected)

    def test_eval_paths_and_boundary_escapes_are_rejected_without_opening_them(self):
        paths = (
            "eval/dev.json", "eval/test.json", "eval/LOCK.json",
            "docs/problem.md", "runs/question-design", "runs/question-design/.",
            "runs/question-design/..", "runs/question-design/../../../eval/test.json",
            "runs/question-design-sibling/candidates.json",
            str((ROOT / "eval" / "test.json").resolve()),
            str((ROOT.parent / "outside-question-design.json").resolve()),
        )
        for path in paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    self.mod.run_path(path)


if __name__ == "__main__":
    unittest.main()

"""장소 한국어명 대응표(data/processed/location_names_ko_red_blue.json)를 입력 데이터와 대조한다 (네트워크 없음)."""
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "data" / "processed" / "location_names_ko_red_blue.json"
ENCOUNTERS = ROOT / "data" / "processed" / "encounters_red_blue.json"
ACQUISITION = ROOT / "data" / "processed" / "machine_acquisition_red_blue.json"
MANIFEST = ROOT / "data" / "source_manifest.json"
GENERATOR = ROOT / "scripts" / "helper" / "build_location_names_ko_red_blue.py"
ALLOWED_REVIEW = {"pending", "approved", "rejected"}
# 사용자 승인 결과: 전체 168항목 approved, 홍련섬/홍련마을은 '홍련섬'으로 사용자 결정. confidence는 승인과 별개라 그대로다.
EXPECTED_CONFIDENCE = {"confirmed": 138, "uncertain": 30}
CINNABAR_IDS = {"pokeapi_location:cinnabar-island", "pokeapi_location_area:cinnabar-island-area",
                "pokeapi_location_area:cinnabar-island-cinnabar-lab", "pokered_map:CinnabarLabMetronomeRoom"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class LocationNamesKoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load(TABLE)
        cls.entries = cls.doc["entries"]
        encounters = load(ENCOUNTERS)
        cls.locations, cls.areas = set(), set()
        for pokemon in encounters["pokemon"]:
            for version in encounters["versions"]:
                for item in pokemon["versions"][version]["encounters"]:
                    cls.locations.add(item["location"]["name"])
                    cls.areas.add(item["location_area"]["name"])
        cls.maps = {loc["map_id_raw"] for m in load(ACQUISITION)["machines"] for loc in m["locations"]}

    def ids_of(self, kind):
        return [e["identifier"] for e in self.entries if e["identifier_kind"] == kind]

    def test_every_identifier_exactly_once(self):
        for kind, expected in (("pokeapi_location", self.locations), ("pokeapi_location_area", self.areas),
                               ("pokered_map", self.maps)):
            with self.subTest(kind):
                found = self.ids_of(kind)
                self.assertEqual(len(found), len(set(found)), "중복")
                self.assertEqual(set(found), expected, "누락·초과")
        self.assertEqual((len(self.locations), len(self.areas), len(self.maps)), (45, 74, 49))
        self.assertEqual(len(self.entries), 45 + 74 + 49)
        self.assertEqual({e["identifier_kind"] for e in self.entries},
                         {"pokeapi_location", "pokeapi_location_area", "pokered_map"})
        ids = [e["id"] for e in self.entries]
        self.assertEqual(len(ids), len(set(ids)))
        for e in self.entries:
            self.assertEqual(e["id"], f"{e['identifier_kind']}:{e['identifier']}")

    def test_names_sources_and_status(self):
        for e in self.entries:
            with self.subTest(e["id"]):
                self.assertIn(e["review_status"], ALLOWED_REVIEW)
                if e["name_ko"] is None:
                    self.assertIsNone(e["composition"])
                    self.assertIsNone(e["confidence"])
                    continue
                self.assertTrue(e["name_ko"].strip())
                self.assertTrue(e["sources"], "한국어명에 출처가 없다")
                for source in e["sources"]:
                    self.assertTrue(source["url"].startswith("https://"))
                    self.assertIn("oldid=", source["url"])
                self.assertIn(e["composition"], ("official", "composed"))
                self.assertIn(e["confidence"], ("confirmed", "uncertain"))
                self.assertTrue(e["game_basis"])
        self.assertEqual(set(self.doc["review_statuses"]), ALLOWED_REVIEW)

    def test_user_approval_recorded(self):
        self.assertEqual({e["review_status"] for e in self.entries}, {"approved"})
        review = self.doc["review"]
        self.assertEqual((review["status"], review["approved_by"]), ("approved", "user"))
        self.assertEqual((review["entries_approved"], review["entries_total"]), (168, 168))
        self.assertTrue(any("홍련섬" in decision and "사용자 결정" in decision for decision in review["decisions"]))
        self.assertEqual(self.doc["summary"]["confidence"], EXPECTED_CONFIDENCE)
        cinnabar = {e["id"]: e for e in self.entries if "cinnabar-island" in e["parent_keys"]}
        self.assertEqual(set(cinnabar), CINNABAR_IDS)
        for e in cinnabar.values():
            self.assertTrue(e["name_ko"].startswith("홍련섬"), e["id"])
            self.assertNotIn("홍련마을", e["name_ko"])
            self.assertIn("사용자 결정: '홍련섬'으로 확정", e["note"])
            self.assertEqual(e["confidence"], "uncertain")
        self.assertIn("사용자 결정", self.doc["parents"]["cinnabar-island"]["note"])

    def test_summary_matches_entries(self):
        summary = self.doc["summary"]
        self.assertEqual(summary["total"], len(self.entries))
        self.assertEqual(summary["name_ko_null"], sum(1 for e in self.entries if e["name_ko"] is None))
        for value, count in summary["confidence"].items():
            self.assertEqual(count, sum(1 for e in self.entries if e["confidence"] == value))
        for value, count in summary["composition"].items():
            self.assertEqual(count, sum(1 for e in self.entries if e["composition"] == value))

    def test_inputs_and_manifest(self):
        for item in self.doc["inputs"]:
            self.assertEqual(item["sha256"], hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest())
        entry = next(e for e in load(MANIFEST)["processed_files"]
                     if e["source_id"] == "processed:location_names_ko_red_blue")
        data = TABLE.read_bytes()
        self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(entry["bytes"], len(data))
        self.assertNotIn(b"\r\n", data)
        example = entry["example"]
        pointer_index = int(example["pointer"].rsplit("/", 1)[1])
        self.assertEqual(self.entries[pointer_index]["id"], example["identity_value"])
        self.assertEqual(entry["identity"]["record_count"], len(self.entries))

    def test_saved_json_equals_regeneration(self):
        spec = importlib.util.spec_from_file_location("build_location_names_ko_red_blue", GENERATOR)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.render(module.build_document()).encode("utf-8"), TABLE.read_bytes())


if __name__ == "__main__":
    unittest.main()

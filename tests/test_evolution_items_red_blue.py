"""evolution_items_red_blue.json을 evolutions_red_blue.json과 대조한다 (네트워크 없음)."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"


def _resolve_pointer(doc, pointer):
    node = doc
    for part in pointer.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


class EvolutionItemsRedBlueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evolutions = json.loads((PROCESSED / "evolutions_red_blue.json").read_text(encoding="utf-8"))
        cls.data = json.loads((PROCESSED / "evolution_items_red_blue.json").read_text(encoding="utf-8"))
        cls.items = cls.data["items"]
        # evolutions 파일에서 use-item 관계를 직접 뽑는다: {item: {(from_id, to_id), ...}}
        cls.expected = {}
        cls.expected_count = 0
        for record in cls.evolutions["records"]:
            for edge in record["evolves_to"]:
                if edge["trigger"] == "use-item":
                    cls.expected.setdefault(edge["item"], set()).add((edge["from_id"], edge["to_id"]))
                    cls.expected_count += 1

    def test_every_use_item_appears_exactly_once(self):
        names = [item["name"] for item in self.items]
        for item_name in self.expected:
            self.assertEqual(names.count(item_name), 1, item_name)
        self.assertEqual(set(names), set(self.expected))
        self.assertEqual(self.data["item_count"], len(self.items))

    def test_names_present(self):
        for item in self.items:
            self.assertIsInstance(item["name_ko"], str, item["name"])
            self.assertTrue(item["name_ko"].strip(), item["name"])
            self.assertIsInstance(item["name_en"], str, item["name"])
            self.assertTrue(item["name_en"].strip(), item["name"])
            self.assertEqual(item["source_url"], f"https://pokeapi.co/api/v2/item/{item['name']}/")

    def test_usages_match_evolutions(self):
        for item in self.items:
            pairs = [(u["from_id"], u["to_id"]) for u in item["used_in"]]
            self.assertEqual(len(pairs), len(set(pairs)), item["name"])
            self.assertEqual(set(pairs), self.expected[item["name"]], item["name"])
        total = sum(len(item["used_in"]) for item in self.items)
        self.assertEqual(total, self.expected_count)
        self.assertEqual(self.data["usage_count"], self.expected_count)

    def test_evolution_pointers_resolve(self):
        for item in self.items:
            for usage in item["used_in"]:
                edge = _resolve_pointer(self.evolutions, usage["evolution_pointer"])
                self.assertEqual(
                    (edge["from_id"], edge["to_id"], edge["trigger"], edge["item"], edge["from_name"], edge["to_name"]),
                    (usage["from_id"], usage["to_id"], "use-item", item["name"], usage["from_name"], usage["to_name"]),
                )

    def test_deterministic_order(self):
        self.assertEqual(self.items, sorted(self.items, key=lambda i: (i["id"], i["name"])))
        self.assertEqual(len({i["id"] for i in self.items}), len(self.items))
        for item in self.items:
            self.assertEqual(item["used_in"], sorted(item["used_in"], key=lambda u: (u["from_id"], u["to_id"])))


if __name__ == "__main__":
    unittest.main()

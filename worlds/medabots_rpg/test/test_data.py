"""The shipped game data must be consistent and its permanent IDs must never change."""
import copy
import unittest

from ..data_loader import DataError, DictDataSource, get_world_data, load_world_data
from .support import raw_data


class TestShippedData(unittest.TestCase):
    data = get_world_data()

    def test_documented_table_sizes(self):
        tables = self.data.tables
        self.assertEqual(len(tables.bots), 120)
        self.assertEqual(len(tables.parts), 120)
        self.assertEqual(len(tables.medals), 30)
        self.assertEqual(len(tables.maps), 192)
        self.assertEqual(len(tables.characters), 96)
        self.assertEqual(len(tables.opcode_lengths), 137)
        self.assertEqual(tables.opcode_lengths[0x3C], 2)  # "give medal"

    def test_item_counts(self):
        kinds = [item.kind for item in self.data.items]
        self.assertEqual(kinds.count("part"), 480)
        self.assertEqual(kinds.count("medal"), 30)

    def test_permanent_ids_do_not_change(self):
        """These IDs are baked into multiworlds and player saves. Renumbering one breaks every existing seed."""
        by_name = self.data.item_by_name
        self.assertEqual(by_name["Head: Psycho Missile (Noctobat)"].id, 10000)
        self.assertEqual(by_name["Right Arm: Electo Missile (Noctobat)"].id, 10001)
        self.assertEqual(by_name["Medal: Kuwagata"].id, 11000)
        self.assertEqual(by_name["Medal: Kabuto"].id, 11001)
        self.assertEqual(by_name["Money Pouch (Small)"].id, 12001)
        self.assertEqual(by_name["Money Drain Trap"].id, 13001)
        self.assertEqual(self.data.location_by_name["Research Center - Nae's Medal Room Medal"].id, 20001)
        self.assertEqual(self.data.location_by_name["Odoro Marsh - Squidguts Battle Reward"].id, 20003)

    def test_every_map_belongs_to_exactly_one_area(self):
        for map_name in self.data.tables.maps:
            owners = [a.name for a in self.data.areas if a.owns_map(map_name)]
            self.assertEqual(len(owners), 1, f"{map_name!r} -> {owners}")

    def test_names_are_clean(self):
        for name in [i.name for i in self.data.items] + [loc.name for loc in self.data.locations]:
            self.assertEqual(name, name.strip())
            self.assertNotIn("  ", name)
            self.assertLessEqual(len(name), 80, name)

    def test_unverified_data_is_not_marked_verified(self):
        """The shipped data has never been checked against a ROM, so it must say so (it drives the gate)."""
        self.assertFalse(self.data.is_verified)
        self.assertFalse(self.data.memory_map.verified)
        self.assertTrue(all(not loc.verified for loc in self.data.locations))

    def test_story_areas_form_one_chain(self):
        parents = [a.parent for a in self.data.areas]
        self.assertEqual(parents[0], None)
        self.assertEqual(parents[1:], [a.name for a in self.data.areas[:-1]])
        self.assertEqual(self.data.areas[-1].clear_event, self.data.goal_event)


class TestValidation(unittest.TestCase):
    """The validator must reject broken data with a message naming the problem."""

    def load(self, mutate):
        raw = copy.deepcopy(raw_data())
        mutate(raw)
        return load_world_data(DictDataSource(raw))

    def assertRejected(self, mutate, fragment):
        with self.assertRaises(DataError) as caught:
            self.load(mutate)
        self.assertIn(fragment, str(caught.exception))

    def test_unmodified_data_loads(self):
        self.load(lambda raw: None)

    def test_duplicate_location_id(self):
        def mutate(raw):
            raw["locations"]["locations"][1]["id"] = raw["locations"]["locations"][0]["id"]
        self.assertRejected(mutate, "duplicate location id")

    def test_duplicate_location_name(self):
        def mutate(raw):
            raw["locations"]["locations"][1]["name"] = raw["locations"]["locations"][0]["name"]
        self.assertRejected(mutate, "duplicate location name")

    def test_unknown_map(self):
        def mutate(raw):
            raw["locations"]["locations"][0]["map"] = "Nowhere"
        self.assertRejected(mutate, "belongs to no area")

    def test_unknown_category(self):
        def mutate(raw):
            raw["locations"]["locations"][0]["category"] = "mystery"
        self.assertRejected(mutate, "unknown category")

    def test_verified_location_needs_detect(self):
        def mutate(raw):
            raw["locations"]["locations"][0]["status"] = "verified"
        self.assertRejected(mutate, "verified but has no 'detect'")

    def test_verified_memory_map_must_be_complete(self):
        def mutate(raw):
            raw["memory_map"]["verified"] = True
        self.assertRejected(mutate, "marked verified but is missing")

    def test_unowned_map(self):
        def mutate(raw):
            raw["regions"]["areas"][0]["map_prefixes"].remove("Old Factory")
        self.assertRejected(mutate, "'Old Factory' is owned by 0 areas")

    def test_area_declared_before_its_parent(self):
        def mutate(raw):
            raw["regions"]["areas"][1]["from"] = "Ninja Park"
        self.assertRejected(mutate, "must be listed after its parent")

    def test_unknown_rule_item(self):
        def mutate(raw):
            raw["locations"]["locations"][0]["requires"] = "No Such Item"
        self.assertRejected(mutate, "unknown item or event")

    def test_malformed_rule(self):
        def mutate(raw):
            raw["locations"]["locations"][0]["requires"] = {"all": "Story Complete"}
        self.assertRejected(mutate, "needs a list")

    def test_trap_with_unknown_requirement(self):
        def mutate(raw):
            raw["items"]["traps"][0]["requires"] = ["tables.nonsense"]
        self.assertRejected(mutate, "unknown memory map entry")

    def test_unknown_version_exclusive_bot(self):
        def mutate(raw):
            raw["items"]["version_exclusive"]["metabee"]["bots"].append("Knight Armor")
        self.assertRejected(mutate, "unknown bot")

    def test_neutralize_must_keep_length(self):
        def mutate(raw):
            raw["locations"]["locations"][0]["neutralize"] = {"offset": "0x10", "expect": "3c0f", "replace": "00"}
        self.assertRejected(mutate, "same length")

    def test_invalid_json(self):
        class Broken(DictDataSource):
            def read(self, name):
                return b"{not json" if name == "rules" else super().read(name)
        with self.assertRaises(DataError):
            load_world_data(Broken(raw_data()))

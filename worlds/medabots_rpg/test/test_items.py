"""Item pool construction, allocation and battle-logic gates."""
import random
import unittest

from BaseClasses import ItemClassification
from rule_builder.rules import And, Has, HasGroup, Or, True_

from ..constants import GROUP_PARTS
from ..data_loader import DataError, DictDataSource, get_world_data, load_world_data
from ..items import allocate, build_item_pool, eligible_parts_and_medals, item_classification, supported_traps
from ..rules import compile_rule, part_gate_thresholds
from .support import gendered_data, make_options, raw_data, verified_data

DATA = get_world_data()
KINDS = {item.name: item.kind for item in DATA.items}


def kinds_in(pool):
    return [KINDS[name] for name in pool.item_names]


class TestAllocate(unittest.TestCase):
    def test_proportional_split_that_sums_to_the_total(self):
        result = allocate(100, {"a": 55, "b": 25, "c": 20}, {})
        self.assertEqual(result, {"a": 55, "b": 25, "c": 20})
        self.assertEqual(sum(allocate(7, {"a": 1, "b": 1, "c": 1}, {}).values()), 7)

    def test_a_capped_key_hands_its_surplus_to_the_others(self):
        result = allocate(100, {"a": 50, "b": 50}, {"a": 10})
        self.assertEqual(result, {"a": 10, "b": 90})

    def test_zero_weights_are_never_used(self):
        self.assertEqual(allocate(10, {"a": 1, "b": 0}, {}), {"a": 10, "b": 0})

    def test_everything_capped_leaves_the_rest_unplaced(self):
        self.assertEqual(sum(allocate(10, {"a": 1, "b": 1}, {"a": 2, "b": 3}).values()), 5)

    def test_nothing_to_place(self):
        self.assertEqual(allocate(0, {"a": 1}, {}), {"a": 0})
        self.assertEqual(allocate(5, {"a": 0}, {}), {"a": 0})


class TestPool(unittest.TestCase):
    def build(self, slots, filler_only=0, seed=1, **options):
        return build_item_pool(DATA, make_options(**options), slots, filler_only, random.Random(seed))

    def test_the_pool_always_has_exactly_one_item_per_slot(self):
        rng = random.Random(7)
        for _ in range(200):
            slots = rng.randint(1, 300)
            filler = rng.randint(0, slots)
            options = {"part_weight": rng.randint(0, 100), "medal_weight": rng.randint(0, 100),
                       "money_weight": rng.randint(0, 100), "trap_percentage": rng.randint(0, 100),
                       "goal": rng.choice(["story_complete", "collect_medals", "collect_medaparts"]),
                       "goal_medal_count": rng.randint(1, 28), "goal_part_count": rng.randint(1, 480)}
            pool = self.build(slots, filler, seed=rng.random(), **options)
            self.assertEqual(len(pool.item_names), slots, options)

    def test_parts_and_medals_are_never_duplicated(self):
        pool = self.build(300, part_weight=100, medal_weight=100, money_weight=0)
        unique = [name for name in pool.item_names if KINDS[name] in ("part", "medal")]
        self.assertEqual(len(unique), len(set(unique)))

    def test_default_split_follows_the_weights(self):
        pool = self.build(100, trap_percentage=0)
        kinds = kinds_in(pool)
        self.assertEqual((kinds.count("part"), kinds.count("medal"), kinds.count("consumable")), (55, 25, 20))

    def test_all_zero_weights_fall_back_to_money(self):
        pool = self.build(10, part_weight=0, medal_weight=0, money_weight=0, trap_percentage=0)
        self.assertEqual(set(kinds_in(pool)), {"consumable"})

    def test_excluded_locations_get_enough_filler(self):
        pool = self.build(20, filler_only=9, part_weight=100, medal_weight=0, money_weight=0, trap_percentage=0)
        self.assertGreaterEqual(sum(k in ("consumable", "trap") for k in kinds_in(pool)), 9)

    def test_collection_goal_reserves_its_items(self):
        pool = self.build(40, goal="collect_medals", goal_medal_count=12, medal_weight=0)
        self.assertEqual(kinds_in(pool).count("medal"), 12)
        self.assertEqual(pool.goal_medal_count, 12)
        pool = self.build(40, goal="collect_medaparts", goal_part_count=30, part_weight=0)
        self.assertEqual(kinds_in(pool).count("part"), 30)

    def test_collection_goal_is_lowered_to_fit_and_says_so(self):
        pool = self.build(6, goal="collect_medals", goal_medal_count=20)
        self.assertEqual(pool.goal_medal_count, 6)
        self.assertTrue(any("lowered" in note for note in pool.notes))
        self.assertEqual(self.build(30, goal="story_complete").goal_medal_count, 0)

    def test_version_exclusive_and_placeholder_items_are_left_out_by_default(self):
        parts, medals = eligible_parts_and_medals(DATA, make_options())
        self.assertFalse(any(item.version_exclusive for item in parts + medals))
        names = {item.name for item in medals}
        self.assertNotIn("Medal: ?", names)
        self.assertNotIn("Medal: !", names)
        self.assertEqual(len(parts), 480 - 6 * 4)
        parts, medals = eligible_parts_and_medals(DATA, make_options(include_version_exclusives=True))
        self.assertEqual((len(parts), len(medals)), (480, 28))

    def test_traps_replace_the_requested_share_of_filler(self):
        pool = self.build(100, part_weight=0, medal_weight=0, money_weight=100, trap_percentage=40)
        self.assertEqual(kinds_in(pool).count("trap"), 40)
        pool = self.build(100, part_weight=0, medal_weight=0, money_weight=100, trap_percentage=0)
        self.assertEqual(kinds_in(pool).count("trap"), 0)

    def test_trap_weights_choose_the_traps(self):
        pool = self.build(50, part_weight=0, medal_weight=0, money_weight=100, trap_percentage=100,
                          trap_weights={"Ambush Trap": 0, "Money Drain Trap": 1, "Rusty Armor Trap": 0,
                                        "Medal Nap Trap": 0})
        self.assertEqual(set(pool.item_names), {"Money Drain Trap"})

    def test_no_trap_weights_means_no_traps(self):
        pool = self.build(50, money_weight=100, trap_percentage=100,
                          trap_weights={name: 0 for name in ("Ambush Trap", "Money Drain Trap", "Rusty Armor Trap",
                                                              "Medal Nap Trap")})
        self.assertEqual(kinds_in(pool).count("trap"), 0)

    def test_traps_the_client_cannot_apply_are_dropped_in_a_verified_build(self):
        data = verified_data(with_optional=False)
        self.assertEqual([t.name for t in supported_traps(data)], ["Money Drain Trap"])
        pool = build_item_pool(data, make_options(money_weight=100, part_weight=0, medal_weight=0,
                                                  trap_percentage=100), 30, 0, random.Random(3))
        self.assertEqual(set(pool.item_names), {"Money Drain Trap"})

    def test_an_unverified_memory_map_keeps_all_traps_so_it_can_be_tested(self):
        raw = raw_data()
        raw["memory_map"]["verified"] = False
        self.assertEqual(len(supported_traps(load_world_data(DictDataSource(raw)))), 4)

    def test_the_calibrated_memory_map_supports_money_drain_and_ambush(self):
        """The game has no armor scale or medal switch, so Rusty Armor and Medal Nap are dropped."""
        self.assertEqual([t.name for t in supported_traps(DATA)], ["Money Drain Trap", "Ambush Trap"])

    def test_a_request_for_only_unsupported_traps_is_reported(self):
        data = verified_data(with_optional=False)
        options = make_options(money_weight=100, part_weight=0, medal_weight=0, trap_percentage=100,
                               trap_weights={"Rusty Armor Trap": 1, "Money Drain Trap": 0, "Medal Nap Trap": 0,
                                             "Ambush Trap": 0})
        pool = build_item_pool(data, options, 10, 0, random.Random(1))
        self.assertEqual(kinds_in(pool).count("trap"), 0)
        self.assertTrue(any("cannot apply" in note for note in pool.notes))

    def test_same_seed_same_pool(self):
        self.assertEqual(self.build(50, seed=5).item_names, self.build(50, seed=5).item_names)
        self.assertNotEqual(self.build(50, seed=5).item_names, self.build(50, seed=6).item_names)


class TestGates(unittest.TestCase):
    per_area = {area.name: 3 for area in DATA.areas}

    def test_mode_off_has_no_gates(self):
        self.assertEqual(part_gate_thresholds(DATA, "off", 100, self.per_area), {})

    def test_the_first_area_is_never_gated(self):
        self.assertNotIn(DATA.areas[0].name, part_gate_thresholds(DATA, "standard", 400, self.per_area))

    def test_gates_grow_with_story_progress_and_with_difficulty(self):
        relaxed = part_gate_thresholds(DATA, "relaxed", 300, {a.name: 20 for a in DATA.areas})
        standard = part_gate_thresholds(DATA, "standard", 300, {a.name: 20 for a in DATA.areas})
        values = [standard.get(a.name, 0) for a in DATA.areas]
        self.assertEqual(values, sorted(values))
        self.assertTrue(all(standard[name] >= relaxed[name] for name in relaxed))
        self.assertEqual(standard[DATA.areas[-1].name], round(300 * 0.30))

    def test_a_gate_never_exceeds_what_earlier_areas_can_hold(self):
        """The property that makes gates safe: enough locations exist before a gate to hold the parts it needs."""
        rng = random.Random(11)
        for _ in range(300):
            per_area = {area.name: rng.randint(0, 12) for area in DATA.areas}
            parts = rng.randint(0, 480)
            for mode in ("relaxed", "standard"):
                gates = part_gate_thresholds(DATA, mode, parts, per_area)
                earlier = 0
                for area in DATA.areas:
                    self.assertLessEqual(gates.get(area.name, 0), earlier // 2, (mode, per_area, parts))
                    self.assertLessEqual(gates.get(area.name, 0), parts)
                    earlier += per_area[area.name]

    def test_no_parts_means_no_gates(self):
        self.assertEqual(part_gate_thresholds(DATA, "standard", 0, self.per_area), {})


class TestRuleCompilation(unittest.TestCase):
    def test_every_expression_form(self):
        self.assertIsInstance(compile_rule(None), True_)
        self.assertIsInstance(compile_rule("Riverview Cleared"), Has)
        self.assertIsInstance(compile_rule({"has": "Medal: Cat", "count": 2}), Has)
        self.assertIsInstance(compile_rule({"group": GROUP_PARTS, "count": 5}), HasGroup)
        self.assertIsInstance(compile_rule({"all": ["Riverview Cleared", {"any": ["Castle Cleared"]}]}), And)
        self.assertIsInstance(compile_rule({"any": ["Riverview Cleared"]}), Or)

    def test_unknown_expression(self):
        with self.assertRaises(DataError):
            compile_rule({"banana": 1})
        with self.assertRaises(DataError):
            compile_rule(42)


class TestPartGenders(unittest.TestCase):
    """Ikki's first Tinpet is male and cannot fit female parts (play-test), so only parts that fit drive the logic."""

    data = gendered_data()

    def part(self, gender):
        return next(i for i in self.data.items if i.kind == "part" and i.data["gender"] == gender)

    def test_battle_logic_only_needs_parts_that_fit(self):
        options = make_options(battle_logic="standard")
        self.assertEqual(item_classification(self.part("male"), options), ItemClassification.progression)
        self.assertEqual(item_classification(self.part("female"), options), ItemClassification.useful)

    def test_collect_medaparts_counts_every_part_whatever_its_gender(self):
        options = make_options(goal="collect_medaparts", battle_logic="standard")
        self.assertEqual(item_classification(self.part("female"), options), ItemClassification.progression)

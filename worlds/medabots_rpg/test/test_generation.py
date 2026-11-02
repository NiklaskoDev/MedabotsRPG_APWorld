"""Whole-world generation for different option sets. Each class also runs Archipelago's standard suite."""
import dataclasses
import io
import json
import os
import tempfile
import zipfile
from unittest import mock

from BaseClasses import ItemClassification, LocationProgressType
from Options import OptionError

from .. import MedabotsRPGWorld
from ..constants import GAME_NAME
from ..locations import progress_type
from ..options import MedabotsOptions
from . import MedabotsTestBase
from .support import make_options, unverified_data

NO_LOCATIONS = {
    "shuffle_medal_pickups": False, "shuffle_chests_and_pickups": False, "shuffle_npc_gifts": False,
    "shuffle_boss_rewards": False,
}
ALL_LOCATIONS = {"shopsanity": True, "shuffle_minigame_prizes": True, "trainer_robattles": True}


def item_names(world_test):
    return [item.name for item in world_test.multiworld.itempool]


class TestDefaults(MedabotsTestBase):
    def test_one_item_per_location(self):
        real = [loc for loc in self.multiworld.get_locations(self.player) if loc.address is not None]
        self.assertEqual(len(self.multiworld.itempool), len(real))
        self.assertEqual(len(real), 9)  # the default categories hold 11 rows, two of them absent from the game

    def test_the_story_chain_is_beatable_only_with_everything(self):
        self.assertBeatable(False)
        self.collect_all_but([])
        self.assertBeatable(True)

    def test_story_events_are_locked_to_their_event_locations(self):
        events = [loc for loc in self.multiworld.get_locations(self.player) if loc.address is None]
        self.assertEqual(len(events), len(self.world.data.areas))
        self.assertTrue(all(loc.item and loc.locked and loc.item.advancement for loc in events))

    def test_parts_are_progression_while_battle_logic_is_on(self):
        part = next(i for i in self.world.data.items if i.kind == "part")
        self.assertEqual(self.world.create_item(part.name).classification, ItemClassification.progression)
        medal = next(i for i in self.world.data.items if i.kind == "medal")
        self.assertEqual(self.world.create_item(medal.name).classification, ItemClassification.useful)
        self.assertEqual(self.world.create_item("Money Pouch (Small)").classification, ItemClassification.filler)
        self.assertEqual(self.world.create_item("Ambush Trap").classification, ItemClassification.trap)

    def test_slot_data_is_json_and_complete(self):
        slot_data = json.loads(json.dumps(self.world.fill_slot_data()))
        self.assertEqual(slot_data["goal"], "story_complete")
        self.assertEqual(slot_data["data_hash"], self.world.data.content_hash)
        self.assertFalse(slot_data["unverified_build"])
        for key in ("world_version", "seed_name", "area_part_gates", "trap_strength", "receive_item_messages"):
            self.assertIn(key, slot_data)

    def test_spoiler_lists_the_part_requirements(self):
        handle = io.StringIO()
        self.world.write_spoiler(handle)
        self.assertIn("medaparts needed to enter an area", handle.getvalue())

    def test_patch_file_is_written(self):
        with tempfile.TemporaryDirectory() as folder:
            self.world.generate_output(folder)
            (name,) = os.listdir(folder)
            self.assertTrue(name.endswith(".apmedabots"))
            with zipfile.ZipFile(os.path.join(folder, name)) as archive:
                meta = json.loads(archive.read("meta.json"))
        self.assertFalse(meta["allow_unverified"])
        self.assertEqual(meta["data_hash"], self.world.data.content_hash)

    def test_filler_item_is_a_money_pouch(self):
        self.assertTrue(self.world.get_filler_item_name().startswith("Money Pouch"))

    def test_generation_is_deterministic(self):
        first = item_names(self)
        self.world_setup(seed=self.multiworld.seed)
        self.assertEqual(first, item_names(self))


class TestEveryLocationCategory(MedabotsTestBase):
    options = {**MedabotsTestBase.options, **ALL_LOCATIONS, "battle_logic": "standard"}

    def test_every_existing_location_is_created(self):
        real = {loc.name for loc in self.multiworld.get_locations(self.player) if loc.address is not None}
        expected = {loc.name for loc in self.world.data.locations if not loc.absent}
        self.assertEqual(real, expected)
        self.assertTrue(any(loc.absent for loc in self.world.data.locations), "absent rows exist but are skipped")


class TestSingleLocation(MedabotsTestBase):
    options = {**MedabotsTestBase.options, **NO_LOCATIONS, "shuffle_boss_rewards": True}


class TestNoBattleLogic(MedabotsTestBase):
    options = {**MedabotsTestBase.options, "battle_logic": "off"}

    def test_no_gates_and_parts_are_merely_useful(self):
        self.assertEqual(self.world.gates, {})
        part = next(i for i in self.world.data.items if i.kind == "part")
        self.assertEqual(self.world.create_item(part.name).classification, ItemClassification.useful)

    def test_without_gates_the_story_needs_no_items(self):
        """Areas only depend on the previous area's cleared event, so with no gates nothing can be missing."""
        self.assertBeatable(True)


class TestStandardBattleLogic(MedabotsTestBase):
    options = {**MedabotsTestBase.options, **ALL_LOCATIONS, "battle_logic": "standard"}

    def test_late_areas_need_parts(self):
        self.assertTrue(self.world.gates)
        late = self.world.data.areas[-1].name
        self.assertGreater(self.world.gates[late], 0)
        parts = [i.name for i in self.multiworld.itempool if i.name in self.world.item_name_groups["Medaparts"]]
        self.collect_all_but(parts)
        self.assertFalse(self.can_reach_region(late))
        self.collect_by_name(parts)
        self.assertTrue(self.can_reach_region(late))


class TestCollectMedalsGoal(MedabotsTestBase):
    options = {**MedabotsTestBase.options, **ALL_LOCATIONS, "goal": "collect_medals", "goal_medal_count": 6}

    def test_the_goal_needs_exactly_those_medals(self):
        medals = [i.name for i in self.multiworld.itempool if i.name.startswith("Medal: ")]
        self.assertGreaterEqual(len(medals), 6)
        self.collect_all_but(medals)
        self.assertBeatable(False)
        self.collect(self.get_items_by_name(medals[:5]))
        self.assertBeatable(False)
        self.collect(self.get_items_by_name(medals[5:6]))
        self.assertBeatable(True)

    def test_medals_are_progression(self):
        self.assertEqual(self.world.create_item("Medal: Kabuto").classification, ItemClassification.progression)


class TestCollectPartsGoal(MedabotsTestBase):
    options = {**MedabotsTestBase.options, **ALL_LOCATIONS, "goal": "collect_medaparts", "goal_part_count": 8,
               "battle_logic": "off"}

    def test_the_goal_needs_those_parts(self):
        parts = [i.name for i in self.multiworld.itempool if i.name in self.world.item_name_groups["Medaparts"]]
        self.assertGreaterEqual(len(parts), 8)
        self.collect_all_but(parts)
        self.assertBeatable(False)
        self.collect(self.get_items_by_name(parts[:8]))
        self.assertBeatable(True)


class TestImpossibleCollectionGoalIsLowered(MedabotsTestBase):
    options = {**MedabotsTestBase.options, "goal": "collect_medals", "goal_medal_count": 28}

    def test_goal_fits_the_pool(self):
        self.assertEqual(self.world.pool.goal_medal_count, 9)
        self.collect_all_but([])
        self.assertBeatable(True)


class TestTrapsEverywhere(MedabotsTestBase):
    options = {**MedabotsTestBase.options, "money_weight": 100, "part_weight": 0, "medal_weight": 0,
               "trap_percentage": 100}

    def test_all_filler_became_traps(self):
        self.assertTrue(all(name.endswith("Trap") for name in item_names(self)))


class TestMoneyOnlyPool(MedabotsTestBase):
    options = {**MedabotsTestBase.options, "money_weight": 100, "part_weight": 0, "medal_weight": 0,
               "trap_percentage": 0, "battle_logic": "off"}


class TestVersionExclusivesAllowed(MedabotsTestBase):
    options = {**MedabotsTestBase.options, **ALL_LOCATIONS, "include_version_exclusives": True,
               "part_weight": 100, "medal_weight": 0, "money_weight": 0}


class TestPresetsGenerate(MedabotsTestBase):
    """Every WebHost preset must produce a playable-looking seed."""

    def test_each_preset(self):
        from ..options import OPTION_PRESETS
        for name, values in OPTION_PRESETS.items():
            with self.subTest(preset=name):
                self.options = {**MedabotsTestBase.options, **values}
                self.world_setup()
                self.collect_all_but([])
                self.assertBeatable(True)


class TestVerificationGate(MedabotsTestBase):
    """Invariant G1: unverified data must never be generated by accident."""

    auto_construct = False
    run_default_tests = False

    def test_verified_data_needs_no_opt_in(self):
        self.world_setup()
        self.assertFalse(self.world.options.allow_unverified_build)

    def test_refuses_unverified_data_without_opt_in(self):
        with mock.patch.object(MedabotsRPGWorld, "data", unverified_data()), self.assertRaises(OptionError) as caught:
            self.world_setup()
        message = str(caught.exception)
        self.assertIn("allow_unverified_build", message)
        self.assertIn("not been verified", message)

    def test_unverified_data_generates_with_opt_in_and_a_warning(self):
        self.options = {"allow_unverified_build": True}
        with mock.patch.object(MedabotsRPGWorld, "data", unverified_data()), self.assertLogs(level="WARNING") as logs:
            self.world_setup()
            self.assertTrue(self.world.fill_slot_data()["unverified_build"])
        self.assertIn("story goal candidate", "\n".join(logs.output))

    def test_default_options_do_not_opt_in(self):
        self.assertFalse(make_options().allow_unverified_build)


class TestNoLocationsIsAnError(MedabotsTestBase):
    options = {**MedabotsTestBase.options, **NO_LOCATIONS}
    auto_construct = False
    run_default_tests = False

    def test_clear_error_message(self):
        with self.assertRaisesRegex(OptionError, "no locations"):
            self.world_setup()


class TestLocationProgressTypes(MedabotsTestBase):
    def test_missable_locations_only_hold_filler_unless_opted_in(self):
        missable = dataclasses.replace(self.world.data.locations[0], missable=True)
        cautious, reckless = make_options(), make_options(include_missable_locations=True)
        self.assertIs(progress_type(missable, cautious), LocationProgressType.EXCLUDED)
        self.assertIs(progress_type(missable, reckless), LocationProgressType.DEFAULT)
        self.assertIs(progress_type(self.world.data.locations[0], cautious), LocationProgressType.DEFAULT)


class TestWorldRegistration(MedabotsTestBase):
    def test_game_name_and_ids(self):
        self.assertEqual(self.world.game, GAME_NAME)
        self.assertEqual(set(self.world.item_name_to_id), {i.name for i in self.world.data.items})
        self.assertEqual(len(set(self.world.location_name_to_id.values())), len(self.world.location_name_to_id))

    def test_groups_cover_the_item_and_location_pools(self):
        for group in ("Medaparts", "Medals", "Money Pouches", "Traps", "Head Parts", "Noctobat"):
            self.assertIn(group, self.world.item_name_groups)
        self.assertIn("Medabot Island", self.world.location_name_groups)
        self.assertEqual(len(self.world.item_name_groups["Medaparts"]), 480)

    def test_options_dataclass(self):
        self.assertIs(self.world.options_dataclass, MedabotsOptions)
